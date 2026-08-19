# Modelo de datos

## Tablas

### household

`id`, `name`

### person

`id`, `household_id`, `name`, `telegram_user_id` (nullable, unique), `role` (`a` | `b`)

Role `a`/`b` corresponde a `PERSON_A_*` y `PERSON_B_*` del `.env`.

### expense

- `household_id`
- `created_by_person_id` — quién mandó el mensaje
- `paid_by_person_id` — quién pagó (visibilidad, no un préstamo)
- `split_type` — `shared` (conjunto del hogar) | `personal` (gasto propio)
- `kind` — `expense` | `invoice`
- `status` — `pending_confirm` | `confirmed` | `rejected`
- `spent_on` — fecha del gasto
- `amount_total` — `Numeric(12, 2)`
- `currency` — USD
- `merchant`, `description`, `category`
- `confidence` — 0–1 del LLM
- `telegram_chat_id`, `telegram_message_id`
- `source_file_path`
- `notes`
- `created_at`, `updated_at`

### invoice_detail

Solo si `kind=invoice`: `ruc`, `legal_name`, `invoice_number`, `authorization_sri`, `subtotal`, `iva_amount`, `iva_rate`, `items_json`.

## Categorías v1

`comida`, `supermercado`, `transporte`, `vivienda`, `servicios`, `salud`, `educacion`, `entretenimiento`, `ropa`, `mascotas`, `otros`

## Recuento (no es deuda)

Se mira cuánto gastó el hogar y cuánto pagó cada persona:

```text
total_hogar = suma de confirmed del periodo
pagó_A = suma donde paid_by = A
pagó_B = suma donde paid_by = B
```

Nunca se calcula ni se muestra “X le debe a Y”.

