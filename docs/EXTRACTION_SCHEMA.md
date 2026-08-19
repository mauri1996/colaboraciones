# Schema de extracción (LLM)

El modelo **debe** devolver este JSON. Validar con Pydantic en fase 4.

```json
{
  "kind": "expense | invoice",
  "spent_on": "YYYY-MM-DD | null",
  "amount_total": 12.5,
  "currency": "USD",
  "merchant": "string",
  "description": "string",
  "category": "comida",
  "split_type": "shared | personal | unknown",
  "paid_by_hint": "a | b | unknown",
  "confidence": 0.86,
  "needs_user_input": ["paid_by", "split_type"],
  "invoice": {
    "ruc": "string|null",
    "legal_name": "string|null",
    "invoice_number": "string|null",
    "authorization_sri": "string|null",
    "subtotal": 10.87,
    "iva_amount": 1.63,
    "iva_rate": 15
  },
  "raw_summary": "1 oración de lo que se vio"
}
```

Si falta monto o `confidence` es baja, el bot pregunta y no confirma.
Si no hay RUC, `kind=expense`.
`shared` = conjunto del hogar. `personal` = gasto propio. `paid_by_hint` es quién pagó, no una deuda.
