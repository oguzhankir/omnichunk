from defusedxml.ElementTree import fromstring
from structlog import get_logger
from typing import Union

from .xml_helpers import parse_money
from ..config import sign_web
from ..models import AliasRegistration, Payment

logger = get_logger()


def handle_notification(xml: str) -> None:
    notification = parse_notification_xml(xml)
    logger.debug('processing-notification', notification=notification)
    notification.save()
    notification.send_signal()


def parse_notification_xml(xml: str) -> Union[AliasRegistration, Payment]:
    
    body = fromstring(xml).find('body')
    transaction = body.find('transaction')
    _user_parameters = transaction.find('userParameters')

    def get_named_parameter(name):
        return _user_parameters.find("parameter[@name='" + name + "']")

    def success():
        return transaction.get('status') == 'success'

    def parse_success():
        # From the spec: sign2 is only returned in the success case
        computed_signature = sign_web(body.get('merchantId'), transaction.find('amount').text,
                                      transaction.find('currency').text,
                                      transaction.find('uppTransactionId').text)

        sign2 = get_named_parameter('sign2').text
        if computed_signature != sign2:
            raise ValueError('sign2 did not match computed signature')

        success = transaction.find('success')
        d = dict(
            response_code=success.find('responseCode').text,
            response_message=success.find('responseMessage').text,
            authorization_code=success.find('authorizationCode').text,
            acquirer_authorization_code=success.find('acqAuthorizationCode').text,
        )
        return {k: v for k, v in d.items() if v is not None}

    def parse_error():
        error = transaction.find('error')
        d = dict(
            error_code=error.find('errorCode').text,
            error_message=error.find('errorMessage').text,
            error_detail=error.find('errorDetail').text)

        acquirer_error_code = get_named_parameter('acqErrorCode')
        if acquirer_error_code is not None:
            d['acquirer_error_code'] = acquirer_error_code.text

        return {k: v for k, v in d.items() if v is not None}

    def parse_common_attributes():
        d = dict(
            transaction_id=transaction.find('uppTransactionId').text,
            merchant_id=body.get('merchantId'),
            client_ref=transaction.get('refno'),
            amount=parse_money(transaction))

        payment_method = transaction.find('pmethod')
        if payment_method is not None:
            d['payment_method'] = payment_method.text

        request_type = transaction.find('reqtype')
        if request_type is not None:
            d['request_type'] = request_type.text

        credit_card_country = get_named_parameter('returnCustomerCountry')
        if credit_card_country is not None:
            d['credit_card_country'] = credit_card_country.text

        expiry_month = get_named_parameter('expm')
        if expiry_month is not None:
            d['expiry_month'] = int(expiry_month.text)

        expiry_year = get_named_parameter('expy')
        if expiry_year is not None:
            d['expiry_year'] = int(expiry_year.text)

        return d

    # End of inner helper functions, we're back inside parse_notification_xml

    use_alias_parameter = get_named_parameter('useAlias')
    if use_alias_parameter is not None and use_alias_parameter.text == 'true':
        # It's an alias registration

        d = dict(parse_common_attributes())

        masked_card_number = get_named_parameter('maskedCC')
        if masked_card_number is not None:
            d['masked_card_number'] = masked_card_number.text

        card_alias = get_named_parameter('aliasCC')
        if card_alias is not None:
            d['card_alias'] = card_alias.text

        if success():
            d['success'] = True
            d.update(parse_success())
        else:
            d['success'] = False
            d.update(parse_error())

        return AliasRegistration(**d)
    else:
        # It's a payment or a charge
        if success():
            d = dict(success=True)
            cardno = get_named_parameter('cardno')
            if cardno is not None:
                d['masked_card_number'] = cardno.text
            d.update(parse_common_attributes())
            d.update(parse_success())
            return Payment(**d)
        else:
            d = dict(success=False)
            d.update(parse_common_attributes())
            d.update(parse_error())
            return Payment(**d)
