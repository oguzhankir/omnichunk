async def asgi_send(self, message: dict) -> None:
        
        if message["type"] == "http.response.start" and self.state == ASGIHTTPState.REQUEST:
            self.response = message
        elif message["type"] == "http.response.body" and self.state in {
            ASGIHTTPState.REQUEST,
            ASGIHTTPState.RESPONSE,
        }:
            if self.state == ASGIHTTPState.REQUEST:
                headers = build_and_validate_headers(self.response["headers"])
                headers.extend(self.response_headers())
                await self.asend(
                    h11.Response(status_code=int(self.response["status"]), headers=headers)
                )
                self.state = ASGIHTTPState.RESPONSE

            if (
                not suppress_body(self.scope["method"], int(self.response["status"]))
                and message.get("body", b"") != b""
            ):
                await self.asend(h11.Data(data=bytes(message["body"])))

            if not message.get("more_body", False):
                if self.state != ASGIHTTPState.CLOSED:
                    await self.asend(h11.EndOfMessage())
                    await self.asgi_put({"type": "http.disconnect"})
                    self.state = ASGIHTTPState.CLOSED
        else:
            raise UnexpectedMessage(self.state, message["type"])
