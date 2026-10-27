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
