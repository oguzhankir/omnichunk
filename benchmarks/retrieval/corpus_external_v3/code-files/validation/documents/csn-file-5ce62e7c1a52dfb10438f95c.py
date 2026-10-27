from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring
from moneyed import Money
import requests
from structlog import get_logger

from .xml_helpers import money_to_amount_and_currency, parse_money
from ..config import datatrans_authorize_url, mpo_merchant_id, sign_mpo
from ..models import AliasRegistration, Payment

logger = get_logger()


def pay_with_alias(amount: Money, alias_registration_id: str, client_ref: str) -> Payment:
    
    if amount.amount <= 0:
        raise ValueError('Pay with alias takes a strictly positive amount')

    alias_registration = AliasRegistration.objects.get(pk=alias_registration_id)

    logger.info('paying-with-alias', amount=amount, client_ref=client_ref,
                alias_registration=alias_registration)

    request_xml = build_pay_with_alias_request_xml(amount, client_ref, alias_registration)

    logger.info('sending-pay-with-alias-request', url=datatrans_authorize_url, data=request_xml)

    response = requests.post(
        url=datatrans_authorize_url,
        headers={'Content-Type': 'application/xml'},
        data=request_xml)

    logger.info('processing-pay-with-alias-response', response=response.content)

    charge_response = parse_pay_with_alias_response_xml(response.content)
    charge_response.save()
    charge_response.send_signal()

    return charge_response


def build_pay_with_alias_request_xml(amount: Money, client_ref: str, alias_registration: AliasRegistration) -> bytes:
    merchant_id = mpo_merchant_id
    client_ref = client_ref

    root = Element('authorizationService')
    root.set('version', '3')

    body = SubElement(root, 'body')
    body.set('merchantId', merchant_id)

    transaction = SubElement(body, 'transaction')
    transaction.set('refno', client_ref)

    request = SubElement(transaction, 'request')

    amount, currency = money_to_amount_and_currency(amount)
    SubElement(request, 'amount').text = str(amount)
    SubElement(request, 'currency').text = currency
    SubElement(request, 'aliasCC').text = alias_registration.card_alias
    SubElement(request, 'expm').text = str(alias_registration.expiry_month)
    SubElement(request, 'expy').text = str(alias_registration.expiry_year)
    SubElement(request, 'reqtype').text = 'CAA'
    SubElement(request, 'sign').text = sign_mpo(merchant_id, amount, currency, client_ref)

    return tostring(root, encoding='utf8')


def parse_pay_with_alias_response_xml(xml: bytes) -> Payment:
    body = fromstring(xml).find('body')
    status = body.get('status')
    transaction = body.find('transaction')
    trx_status = transaction.get('trxStatus')
    request = transaction.find('request')

    common_attributes = dict(
        merchant_id=body.get('merchantId'),
        card_alias=request.find('aliasCC').text,
        expiry_month=int(request.find('expm').text),
        expiry_year=int(request.find('expy').text),
        request_type=request.find('reqtype').text,
        client_ref=transaction.get('refno'),
        amount=parse_money(request)
    )

    if status == 'accepted' and trx_status == 'response':
        response = transaction.find('response')

        transaction_id = response.find('uppTransactionId').text
        masked_card_number = response.find('maskedCC').text
        return_customer_country = response.find('returnCustomerCountry').text

        response_code = response.find('responseCode').text
        response_message = response.find('responseMessage').text
        authorization_code = response.find('authorizationCode').text
        acquirer_authorization_code = response.find('acqAuthorizationCode').text

        d = dict(
            success=True,
            transaction_id=transaction_id,
            masked_card_number=masked_card_number,
            credit_card_country=return_customer_country,
            response_code=response_code,
            response_message=response_message,
            authorization_code=authorization_code,
            acquirer_authorization_code=acquirer_authorization_code,
        )
        d.update(common_attributes)
    else:
        error = transaction.find('error')

        d = dict(
            success=False,
            error_code=error.find('errorCode').text,
            error_message=error.find('errorMessage').text,
            error_detail=error.find('errorDetail').text,
            acquirer_error_code=text_or_else(error.find('acqErrorCode')),
            transaction_id=error.find('uppTransactionId').text,
            credit_card_country=text_or_else(error.find('returnCustomerCountry')),
        )
        d.update(**common_attributes)
    return Payment(**d)


def text_or_else(element, else_value='') -> str:
    if element is not None:
        return element.text
    else:
        return else_value
