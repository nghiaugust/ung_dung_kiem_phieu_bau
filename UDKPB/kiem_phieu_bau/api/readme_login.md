┌─────────┐                                    ┌─────────┐
│ Client  │                                    │ Server  │
└────┬────┘                                    └────┬────┘
     │                                              │
     │  POST /api/login/                            │
     │  {username, password}                        │
     ├─────────────────────────────────────────────>│
     │                                              │
     │                                              │ 1. Xác thực user/pass
     │                                              │    django.authenticate()
     │                                              │
     │                                              │ 2. Get/Create APIToken
     │                                              │    APIToken.get_or_create(user)
     │                                              │
     │                                              │ 3. Generate tokens
     │                                              │    ┌──────────────────┐
     │                                              │    │ access_token =   │
     │                                              │    │ generate_token() │
     │                                              │    │ (64 chars)       │
     │                                              │    └──────────────────┘
     │                                              │    ┌──────────────────┐
     │                                              │    │ refresh_token =  │
     │                                              │    │ generate_token() │
     │                                              │    │ (64 chars)       │
     │                                              │    └──────────────────┘
     │                                              │
     │                                              │ 4. Hash tokens (Blind Index)
     │                                              │    ┌────────────────────┐
     │                                              │    │ token_hash =       │
     │                                              │    │ SHA256(access)     │
     │                                              │    └────────────────────┘
     │                                              │    ┌────────────────────┐
     │                                              │    │ refresh_token_hash │
     │                                              │    │ = SHA256(refresh)  │
     │                                              │    └────────────────────┘
     │                                              │
     │                                              │ 5. Encrypt tokens (AES-256-GCM)
     │                                              │    ┌─────────────────────┐
     │                                              │    │ encrypted_token =   │
     │                                              │    │ AES_GCM_encrypt(    │
     │                                              │    │   access_token)     │
     │                                              │    └─────────────────────┘
     │                                              │    ┌─────────────────────┐
     │                                              │    │ encrypted_refresh = │
     │                                              │    │ AES_GCM_encrypt(    │
     │                                              │    │   refresh_token)    │
     │                                              │    └─────────────────────┘
     │                                              │
     │                                              │ 6. Save to DB
     │                                              │    ┌──────────────────────┐
     │                                              │    │ DB: api_tokens       │
     │                                              │    ├──────────────────────┤
     │                                              │    │ token: ENCRYPTED     │
     │                                              │    │ token_hash: abc123.. │
     │                                              │    │ expires_at: +1h      │
     │                                              │    │ refresh_token: ENC   │
     │                                              │    │ refresh_token_hash   │
     │                                              │    │ refresh_expires: +30d│
     │                                              │    └──────────────────────┘
     │                                              │
     │  Response:                                   │
     │  {                                           │
     │    access_token: "plaintext64chars",        │
     │    refresh_token: "plaintext64chars",       │
     │    expires_in: 3600,                        │
     │    expires_at: "2025-12-27T15:30:00Z"       │
     │  }                                           │
     │<─────────────────────────────────────────────┤
     │                                              │
     │ 7. Client lưu vào storage                   │
     │    localStorage.set('access_token', ...)    │
     │    localStorage.set('refresh_token', ...)   │
     │    localStorage.set('expires_at', ...)      │
     │                                              │