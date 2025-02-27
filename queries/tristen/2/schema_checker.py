import jsonschema

schema = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": [
      "range_start",
      "range_end",
      "error_rate",
      "project_ids",
      "user_emails",
      "tickets",
      "unresponsed_tickets"
    ],
    "properties": {
      "range_start": {
        "type": "string",
        "format": "date",
        "description": "Start date of the range"
      },
      "range_end": {
        "type": "string",
        "format": "date",
        "description": "End date of the range"
      },
      "error_rate": {
        "type": "number",
        "description": "Average error rate of the highest-error projects",
        "minimum": 0
      },
      "project_ids": {
        "type": "array",
        "items": {
          "type": "string",
          "format": "uuid",
          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        },
        "description": "UUIDs of all projects with the highest error rate",
        "uniqueItems": True,
        "minItems": 1
      },
      "user_emails": {
        "type": "array",
        "items": {
          "type": "string",
          "format": "email",
          "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        },
        "description": "Emails of users who own these projects",
        "uniqueItems": True,
        "minItems": 1
      },
      "tickets": {
        "type": "object",
        "description": "Mapping of user emails to their ticket IDs",
        "patternProperties": {
          "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$": {
            "type": "array",
            "items": {
              "type": "integer",
              "minimum": 1
            },
            "uniqueItems": True,
            "minItems": 0
          }
        },
        "additionalProperties": False
      },
      "unresponsed_tickets": {
        "type": "array",
        "description": "Array of ticket IDs that haven't been responded to by an agent",
        "items": {
          "type": "integer",
          "minimum": 1
        },
        "uniqueItems": True,
        "minItems": 0
      }
    },
    "additionalProperties": False
  },
  "minItems": 1
}


jsonschema.validate([
  {
    "range_start": "2024-11-01",
    "range_end": "2024-11-30",
    "error_rate": 11.305,
    "project_ids": [
      "fd5733c0-f5c4-4fbb-9420-d7aada380bd7"
    ],
    "user_emails": [
      "andrew.stokes@arnold.com"
    ],
    "tickets": {
      "andrew.stokes@arnold.com": [
        278,
        289
      ]
    },
    "unresponsed_tickets": [
      278
    ]
  },
  {
    "range_start": "2024-11-01",
    "range_end": "2024-11-15",
    "error_rate": 15.2775,
    "project_ids": [
      "f7389c16-ec16-4363-a50a-adbc43c69276"
    ],
    "user_emails": [
      "jack.livingston@pham-robbins.com"
    ],
    "tickets": {
      "jack.livingston@pham-robbins.com": []
    },
    "unresponsed_tickets": []
  },
  {
    "range_start": "2024-10-01",
    "range_end": "2024-10-31",
    "error_rate": 8.22272727272727,
    "project_ids": [
      "7df191de-2bc0-41e1-8343-d3bbf5ee5f22"
    ],
    "user_emails": [
      "barbara.gaines@garcia.com"
    ],
    "tickets": {
      "barbara.gaines@garcia.com": []
    },
    "unresponsed_tickets": []
  },
  {
    "range_start": "2024-03-14",
    "range_end": "2024-03-16",
    "error_rate": 8.62,
    "project_ids": [
      "a637db41-11c3-4222-b973-9a56c2fc051c",
      "f8992481-c11f-403d-94d5-0a1949ed4764"
    ],
    "user_emails": [
      "christopher.gomez@knapp-hawkins.net",
      "jerry.white@ferguson.com"
    ],
    "tickets": {
      "christopher.gomez@knapp-hawkins.net": [
        214
      ],
      "jerry.white@ferguson.com": [
        211,
        257,
        283
      ]
    },
    "unresponsed_tickets": [
      257
    ]
  },
  {
    "range_start": "2023-10-15",
    "range_end": "2023-10-18",
    "error_rate": 4.915,
    "project_ids": [
      "4e291cdc-0aab-4573-86a4-c82490831964",
      "ec641134-7b9b-4e2f-a2b9-4a0bb93ba239"
    ],
    "user_emails": [
      "laura.lewis@dodson.com",
      "lisa.fields@graves.com"
    ],
    "tickets": {
      "laura.lewis@dodson.com": [
        206
      ],
      "lisa.fields@graves.com": [
        182, 
        183, 
        184, 
        185, 
        186, 
        279
      ]
    },
    "unresponsed_tickets": [
      182
    ]
  }
], schema)