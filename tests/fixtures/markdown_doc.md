# API Reference

Welcome to the API documentation. This guide covers authentication, endpoints, and error handling.

## Authentication

All requests require an API key passed in the `Authorization` header.

### OAuth Flow

1. Register your application
2. Redirect users to the authorization URL
3. Exchange the code for a token

```python
import requests

def get_token(code: str) -> str:
    response = requests.post("/oauth/token", data={"code": code})
    return response.json()["access_token"]
```

### API Keys

For server-to-server communication, use API keys instead of OAuth.

| Plan | Rate Limit | Concurrent |
|------|-----------|------------|
| Free | 100/min   | 5          |
| Pro  | 1000/min  | 50         |

## Endpoints

### GET /users

Returns a list of users.

**Parameters:**
- `page` (int): Page number
- `limit` (int): Items per page (max 100)

### POST /users

Create a new user.

```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "role": "admin"
}
```

## Error Handling

All errors follow RFC 7807 format:

```json
{
  "type": "https://api.example.com/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "User with ID 123 was not found"
}
```

### Common Error Codes

- **400** Bad Request: Invalid input
- **401** Unauthorized: Missing or invalid auth
- **403** Forbidden: Insufficient permissions
- **404** Not Found: Resource doesn't exist
- **429** Too Many Requests: Rate limit exceeded
