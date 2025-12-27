┌─────────┐                                    ┌─────────┐
│ Client  │                                    │ Server  │
└────┬────┘                                    └────┬────┘
     │                                              │
     │  GET /api/polls/                             │
     │  Authorization: Bearer <access_token>        │
     ├─────────────────────────────────────────────>│
     │                                              │
     │                                              │ 1. Extract token từ header
     │                                              │    token = "abc123..."
     │                                              │
     │                                              │ 2. Hash token (Blind Index)
     │                                              │    ┌────────────────────┐
     │                                              │    │ token_hash =       │
     │                                              │    │ SHA256(token)      │
     │                                              │    └────────────────────┘
     │                                              │
     │                                              │ 3. Query DB với hash
     │                                              │    SELECT * FROM api_tokens
     │                                              │    WHERE token_hash = ?
     │                                              │    AND is_active = true
     │                                              │
     │                                              │ 4. Decrypt token từ DB
     │                                              │    ┌────────────────────┐
     │                                              │    │ plaintext =        │
     │                                              │    │ decrypt_aes_gcm(   │
     │                                              │    │   db_token)        │
     │                                              │    └────────────────────┘
     │                                              │
     │                                              │ 5. So sánh tokens
     │                                              │    if plaintext == token:
     │                                              │       ✅ Valid
     │                                              │
     │                                              │ 6. Check expires_at
     │                                              │    if now < expires_at:
     │                                              │       ✅ Not expired
     │                                              │
     │                                              │ 7. Attach user to request
     │                                              │    request.api_user = user
     │                                              │
     │  Response: {polls: [...]}                    │
     │<─────────────────────────────────────────────┤