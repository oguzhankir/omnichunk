def build_payment_parameters(amount: Money, client_ref: str) -> PaymentParameters:
    
    merchant_id = web_merchant_id
    amount, currency = money_to_amount_and_currency(amount)
    refno = client_ref
    sign = sign_web(merchant_id, amount, currency, refno)

    parameters = PaymentParameters(
        merchant_id=merchant_id,
        amount=amount,
        currency=currency,
        refno=refno,
        sign=sign,
        use_alias=False,
    )

    logger.info('build-payment-parameters', parameters=parameters)

    return parameters
