def make_server(host, port, app=None,
                server_class=AsyncWsgiServer,
                handler_class=AsyncWsgiHandler,
                ws_handler_class=None,
                ws_path='/ws'):
    
    handler_class.ws_handler_class = ws_handler_class
    handler_class.ws_path = ws_path
    httpd = server_class((host, port), RequestHandlerClass=handler_class)
    httpd.set_app(app)
    return httpd
