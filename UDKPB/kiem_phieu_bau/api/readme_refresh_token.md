┌─────────┐                                    ┌─────────┐
│ Client  │                                    │ Server  │
└────┬────┘                                    └────┬────┘
     │                                              │
     │ ⏰ Khi access_token sắp hết hạn              │
     │    (hoặc đã hết hạn)                         │
     │                                              │
     │  POST /api/refresh-token/                    │
     │  {refresh_token: "xyz789..."}                │
     ├─────────────────────────────────────────────>│
     │                                              │
     │                                              │ 1. Hash refresh_token
     │                                              │    ┌────────────────────┐
     │                                              │    │ refresh_hash =     │
     │                                              │    │ SHA256(refresh)    │
     │                                              │    └────────────────────┘
     │                                              │
     │                                              │ 2. Query DB với hash
     │                                              │    SELECT * FROM api_tokens
     │                                              │    WHERE refresh_token_hash = ?
     │                                              │    AND is_active = true
     │                                              │
     │                                              │ 3. Decrypt refresh_token từ DB
     │                                              │    plaintext_refresh = 
     │                                              │    decrypt_aes_gcm(db_refresh)
     │                                              │
     │                                              │ 4. Verify refresh_token
     │                                              │    if plaintext != refresh_token:
     │                                              │       ❌ Invalid
     │                                              │
     │                                              │ 5. Check refresh_expires_at
     │                                              │    if now > refresh_expires_at:
     │                                              │       ❌ Expired (re-login)
     │                                              │
     │                                              │ 6. Generate NEW access_token
     │                                              │    ┌──────────────────┐
     │                                              │    │ new_access =     │
     │                                              │    │ generate_token() │
     │                                              │    └──────────────────┘
     │                                              │
     │                                              │ 7. Hash + Encrypt new token
     │                                              │    new_hash = SHA256(new_access)
     │                                              │    new_encrypted = AES_GCM(new_access)
     │                                              │
     │                                              │ 8. Update DB
     │                                              │    UPDATE api_tokens SET
     │                                              │      token = new_encrypted,
     │                                              │      token_hash = new_hash,
     │                                              │      expires_at = now + 1h
     │                                              │
     │  Response:                                   │
     │  {                                           │
     │    access_token: "new_plaintext",           │
     │    expires_in: 3600,                        │
     │    expires_at: "2025-12-27T16:30:00Z"       │
     │  }                                           │
     │<─────────────────────────────────────────────┤
     │                                              │
     │ 9. Client update storage                    │
     │    localStorage.set('access_token',         │
     │                     new_access)              │
     │                                              │