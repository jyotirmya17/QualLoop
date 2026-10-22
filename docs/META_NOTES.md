# Meta Conversions API (CAPI) for Conversion Leads — Verification Notes

**Verification Date:** 2026-10-22  
**Verified Source:** Meta for Developers (`developers.facebook.com`)  
**Official Reference URLs:**
- Conversion Leads Integration: `https://developers.facebook.com/docs/marketing-api/conversions-api/guides/conversion-leads-integration`
- Conversions API Parameters: `https://developers.facebook.com/docs/marketing-api/conversions-api/parameters`
- Graph API Changelog & Versions: `https://developers.facebook.com/docs/graph-api/changelog`
- Graph API v26.0 Release: `https://developers.facebook.com/docs/graph-api/changelog/v26.0`

---

## 1. Current Meta API Version

- **Current Graph API Version:** `v26.0` (Released July 29, 2026).
- **Supported Versions Range:** `v21.0` through `v26.0`.
- **QualLoop Target Version:** Graph API `v26.0` (with backward compatibility for `v21.0+`).

---

## 2. Event Timing Rules: Reconciling 7-Day vs. 28-Day Windows

There has been confusion regarding whether events must be sent within 7 days or 28 days. Official Meta documentation establishes two completely separate, orthogonal timing windows:

### A. The 7-Day Upload / Ingestion Window (CAPI Transmission Latency)
- **Constraint:** Meta's Conversions API server endpoint requires `now - event_time <= 7 days` (approximately 168 hours).
- **Behavior:** If an event occurred 10 days ago and is transmitted today with `event_time = (now - 10 days)`, Meta's API server will reject or drop the event.
- **System Requirement:** The CRM/feedback loop must transmit stage updates frequently (ideally real-time or daily batch) so that `upload_time - event_time <= 7 days`.

### B. The 28-Day Conversion Attribution Window (Funnel Eligibility)
- **Constraint:** `event_time - lead_creation_time <= 28 days`.
- **Behavior:** For Meta's ad delivery algorithm to optimize for "Conversion Leads" (down-funnel qualification milestones), the qualified stage must naturally occur within 28 days of the initial form submission (`lead_id`).
- **System Requirement:** If a sales cycle takes 60 days to qualify a lead, Meta's optimization model cannot effectively attribute the qualification back to the ad impression. QualLoop validates that qualification occurred within 28 days of lead generation.

---

## 3. Payload Placement of `lead_id`

- **Correct Location:** `user_data.lead_id` (nested inside the `user_data` object).
- **CRITICAL FORMATTING RULE:** Unlike PII fields (`em`, `ph`, `fn`, `ln`), `lead_id` **MUST NOT BE HASHED**. It must be sent as raw plain-text string (15–17 digits) representing the Meta Lead Ad form submission ID.
- **Deviation in Prior Code:** The prior implementation incorrectly placed `lead_id` inside `custom_data` and only put synthetic hashed email/phone in `user_data`. This prevented Meta from natively associating the qualification event with the Lead Ad.
- **Resolution:** `lead_id` is now placed inside `user_data["lead_id"]` as unhashed string, and also mirrored in `custom_data["lead_id"]` for CRM internal tracking.

---

## 4. Required & Supported Payload Fields

### A. Top-Level Event Object
- `event_name` (String, Required): Standard event name for CRM conversions is `"Lead"`, or a custom event name (e.g. `"QualifiedLead"`) mapped in Events Manager.
- `event_time` (Integer, Required): Unix epoch timestamp (seconds) when the lead stage resolved in the CRM. Must not be future-dated and must be within 7 days of upload.
- `action_source` (String, Required): Must be set to `"system_generated"` or `"crm"` for server-to-server CRM events.
- `user_data` (Object, Required): Customer matching identifiers.
- `custom_data` (Object, Optional): Event metadata (`currency`, `value`, `lead_event_source`, etc.).
- `event_id` (String, Optional but Recommended): Deduplication key (corresponds to QualLoop `idempotency_key`).

### B. `user_data` Fields
- `lead_id` (String, Required for Lead Ads CRM feedback): Unhashed Meta Lead ID.
- `em` (Array of String or String, Required if lead_id unavailable): SHA-256 hashed lowercase trimmed email.
- `ph` (Array of String or String, Optional): SHA-256 hashed E.164 phone number.

---

## 5. Verification Status & Remaining Assumptions

| Component | Status | Source / Note |
|---|---|---|
| 7-day upload latency window | **VERIFIED** | Meta CAPI documentation (`now - event_time <= 7 days`) |
| 28-day conversion qualification window | **VERIFIED** | Meta Conversion Leads guide (`event_time - lead_created <= 28 days`) |
| `lead_id` inside `user_data` (unhashed) | **VERIFIED** | Meta CAPI Parameter specification |
| Top-level required fields | **VERIFIED** | Graph API v21.0 - v26.0 specification |
| Graph API version | **VERIFIED** | Current version v26.0 |
| Exact CRM stage custom schema names | **UNVERIFIED** | Custom stage event names depend on individual advertiser's Events Manager configuration |
| Direct HTTP transmission credentials | **UNVERIFIED / DRY-RUN ONLY** | System deliberately runs in dry-run mode without live Meta System User Access Tokens |
