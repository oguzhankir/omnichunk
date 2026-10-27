def build_register_credit_card_parameters(client_ref: str) -> PaymentParameters:
    

    amount = 0
    currency = 'CHF'  # Datatrans requires this value to be filled, so we use this arbitrary currency.
    merchant_id = web_merchant_id
    refno = client_ref
    sign = sign_web(merchant_id, amount, currency, refno)

    parameters = PaymentParameters(
        merchant_id=merchant_id,
        amount=amount,
        currency=currency,
        refno=refno,
        sign=sign,
        use_alias=True,
    )

    logger.info('building-payment-parameters', parameters=parameters)

    return parameters
