// Generated from the local OpenAPI candidate. Do not hand edit.
export const contractOperations = {
  "adminLogin": {
    "path": "/auth/login",
    "method": "POST",
    "permission": null,
    "query": {}
  },
  "adminMe": {
    "path": "/auth/me",
    "method": "GET",
    "permission": null,
    "query": {}
  },
  "adminLogout": {
    "path": "/auth/logout",
    "method": "POST",
    "permission": null,
    "query": {}
  },
  "adminOverview": {
    "path": "/overview",
    "method": "GET",
    "permission": "overview:read",
    "query": {}
  },
  "adminListUsers": {
    "path": "/users",
    "method": "GET",
    "permission": "users:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "created_at:asc",
          "created_at:desc",
          "email:asc",
          "email:desc"
        ],
        "default": "created_at:desc"
      },
      "email": {
        "type": "string",
        "maxLength": 254
      },
      "enabled": {
        "type": "boolean"
      },
      "effective_vip": {
        "type": "boolean"
      }
    }
  },
  "adminGetUser": {
    "path": "/users/{user_id}",
    "method": "GET",
    "permission": "users:read",
    "query": {}
  },
  "adminSetUserAccess": {
    "path": "/users/{user_id}/access",
    "method": "PATCH",
    "permission": "users:access:write",
    "query": {}
  },
  "adminListJobs": {
    "path": "/jobs",
    "method": "GET",
    "permission": "jobs:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "created_at:asc",
          "created_at:desc",
          "updated_at:asc",
          "updated_at:desc"
        ],
        "default": "created_at:desc"
      },
      "user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "public_status": {
        "type": "string",
        "enum": [
          "queued",
          "downloading",
          "merging",
          "done",
          "error"
        ]
      },
      "internal_state": {
        "type": "string",
        "enum": [
          "queued",
          "running",
          "retry_wait",
          "succeeded",
          "failed",
          "needs_review",
          "legacy_hold",
          "legacy_unset"
        ]
      },
      "execution_version": {
        "type": "integer",
        "enum": [
          1,
          2
        ]
      }
    }
  },
  "adminGetJob": {
    "path": "/jobs/{job_id}",
    "method": "GET",
    "permission": "jobs:read",
    "query": {}
  },
  "adminListMemberships": {
    "path": "/memberships",
    "method": "GET",
    "permission": "memberships:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "expires_at:asc",
          "expires_at:desc",
          "user_id:asc"
        ],
        "default": "user_id:asc"
      },
      "user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "effective": {
        "type": "boolean"
      },
      "status": {
        "type": "string",
        "enum": [
          "free",
          "active",
          "expired"
        ]
      }
    }
  },
  "adminListCheckouts": {
    "path": "/billing/checkouts",
    "method": "GET",
    "permission": "billing:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "created_at:asc",
          "created_at:desc"
        ],
        "default": "created_at:desc"
      },
      "user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "state": {
        "type": "string",
        "enum": [
          "pending",
          "open",
          "paid",
          "expired",
          "failed"
        ]
      },
      "reconciliation": {
        "type": "string",
        "enum": [
          "not_started",
          "unknown",
          "verified",
          "needs_review",
          "closed"
        ]
      },
      "fulfilled": {
        "type": "boolean"
      },
      "provider_account_scope": {
        "type": "string",
        "maxLength": 128
      },
      "livemode": {
        "type": "boolean"
      }
    }
  },
  "adminGetCheckout": {
    "path": "/billing/checkouts/{checkout_id}",
    "method": "GET",
    "permission": "billing:read",
    "query": {}
  },
  "adminListPayments": {
    "path": "/billing/payments",
    "method": "GET",
    "permission": "billing:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "id:asc",
          "id:desc"
        ],
        "default": "id:asc"
      },
      "user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "revoked": {
        "type": "boolean"
      },
      "payment_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      }
    }
  },
  "adminGetPayment": {
    "path": "/billing/payments/{payment_id}",
    "method": "GET",
    "permission": "billing:read",
    "query": {}
  },
  "adminListAuditLogs": {
    "path": "/audit/logs",
    "method": "GET",
    "permission": "audit:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "recorded_at:asc",
          "recorded_at:desc"
        ],
        "default": "recorded_at:desc"
      },
      "actor_user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "target_user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      },
      "action": {
        "type": "string",
        "maxLength": 64
      },
      "outcome": {
        "type": "string",
        "enum": [
          "succeeded",
          "denied",
          "failed"
        ]
      },
      "recorded_from": {
        "type": "string",
        "format": "date-time",
        "pattern": "Z$"
      },
      "recorded_before": {
        "type": "string",
        "format": "date-time",
        "pattern": "Z$"
      }
    }
  },
  "adminSystemStatus": {
    "path": "/system/status",
    "method": "GET",
    "permission": "system:read",
    "query": {}
  },
  "adminMeta": {
    "path": "/meta",
    "method": "GET",
    "permission": null,
    "query": {}
  },
  "adminListSupportTickets": {
    "path": "/support/tickets",
    "method": "GET",
    "permission": "support:read",
    "query": {
      "page": {
        "type": "integer",
        "minimum": 1,
        "default": 1
      },
      "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 20
      },
      "sort": {
        "type": "string",
        "enum": [
          "priority:desc",
          "created_at:asc",
          "created_at:desc"
        ],
        "default": "priority:desc"
      },
      "state": {
        "type": "string",
        "enum": [
          "open",
          "resolved",
          "rejected"
        ]
      },
      "category": {
        "type": "string",
        "enum": [
          "membership_not_credited",
          "download_failing",
          "login_problem",
          "other"
        ]
      },
      "priority": {
        "type": "string",
        "enum": [
          "priority",
          "normal"
        ]
      },
      "user_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9_.:-]+$",
        "description": "不透明非空ID，字符串传输；禁止写死实际用户ID、邮箱或供应商对象ID。"
      }
    }
  },
  "adminGetSupportTicket": {
    "path": "/support/tickets/{ticket_id}",
    "method": "GET",
    "permission": "support:read",
    "query": {}
  },
  "adminReplySupportTicket": {
    "path": "/support/tickets/{ticket_id}/reply",
    "method": "POST",
    "permission": "support:write",
    "query": {}
  },
  "adminRejectSupportTicket": {
    "path": "/support/tickets/{ticket_id}/reject",
    "method": "POST",
    "permission": "support:write",
    "query": {}
  },
  "adminVerifySupportPayment": {
    "path": "/support/tickets/{ticket_id}/verify-payment",
    "method": "POST",
    "permission": "support:write",
    "query": {}
  },
  "adminReissueMembership": {
    "path": "/support/tickets/{ticket_id}/reissue",
    "method": "POST",
    "permission": "support:reissue",
    "query": {}
  }
} as const;
