# Meta Conversions API (CAPI) for Conversion Leads — Official Documentation Notes

**Date of Document Review:** 2026-10-22  
**Official Pages Consulted:**
1. `https://developers.facebook.com/documentation/ads-commerce/conversions-api/conversion-leads-integration`
2. `https://developers.facebook.com/documentation/ads-commerce/conversions-api/conversion-leads-integration/crm-integration/3-implementing-the-crm-integration`

---

## 1. Passages Relied Upon & Paraphrases

### A. Business Fit & Eligibility Guidelines
*Source: `conversion-leads-integration` ("Check if your business is a good fit")*
- **Lead Ads format:** The Conversion Leads optimization goal is specifically compatible with Facebook/Instagram Lead Ads (Instant Forms).
- **Volume threshold:** Advertisers must generate at least 200 leads per month.
- **Upload cadence:** Advertisers must be able to upload data regularly, at least once per day.
- **Attribution window:** The target down-funnel stage intended for optimization must occur within 28 days following initial lead generation.
- **Conversion rate bounds:** The target optimization stage must have a conversion rate between 1% and 40% (stages with <1% or >40% conversion are poor fits for model optimization).

### B. Event Architecture & Full Funnel History
*Source: `3-implementing-the-crm-integration` ("3: Implementing the CRM Integration")*
- **Full History vs. Snapshot:** Systems must capture and transmit the complete lead status change history rather than a point-in-time snapshot. If a lead moves through 3 stages between batches, Meta expects 3 distinct events for that lead, plus an initial raw-lead event (e.g., 100 generated leads producing ~215 uploaded events across lifecycle transitions).
- **Chronological Validity:** The `event_time` for any stage transition must be strictly after the lead generation timestamp. Events with timestamps prior to lead creation risk being discarded.

### C. Transmission Latency & Ingestion Window
*Source: `3-implementing-the-crm-integration` ("Note on backfilling and upload timing")*
- **7-day upload latency limit:** Data can only be backfilled for up to 7 days in the past (`upload_time - event_time <= 7 days`). Advertisers are explicitly warned never to manipulate `event_time` to bypass this limit, as timestamps are used for optimization training. Older events are discarded.

### D. Payload Schema & Parameters
*Source: `3-implementing-the-crm-integration` ("Implementing the CRM Integration - Example Payload")*
- **`action_source`:** Must be `"system_generated"`.
- **`user_data`:** Must contain `lead_id` (a 15–17 digit identifier) in raw unhashed form. Standard PII identifiers (such as email or phone) must be SHA-256 hashed if provided.
- **`custom_data`:** Must contain both `lead_event_source` (e.g. CRM name like `"Salesforce"`, `"HubSpot"`, or internal CRM) and `event_source` set to `"crm"`. Events omitting these two parameters will not be registered as Conversion Leads events.
- **`event_name`:** Dynamic lead stage identifier reflecting the stage reached (e.g. `"initial_lead"`, `"contacted"`, `"qualified"`).

### E. Batch Limits & Error Handling
*Source: `3-implementing-the-crm-integration` ("Batch processing")*
- **Batch cap:** Each API batch request can contain a maximum of 1,000 events.
- **Atomic failure behavior:** If a single event within a batch produces an error, Meta may discard the entire batch. Implementations must validate before sending, use conservative batch sizes, and provide error handling/retry logic.

---

## 2. Items NOT On These Two Pages (Marked UNVERIFIED)

| Item | Status | Note |
|---|---|---|
| **Graph API Version (`v26.0`)** | **UNVERIFIED** | Neither page specifies the Graph API version number or version release schedule. |
| **Specific release date of API versions** | **UNVERIFIED** | Not mentioned on either referenced page. |
| **Exact custom event names** | **UNVERIFIED** | Event names are chosen by the advertiser's CRM schema and mapped in Events Manager. |
| **Direct HTTP live transmission endpoint URL** | **UNVERIFIED** | Specific Graph API POST URI (`https://graph.facebook.com/...`) is detailed on general CAPI parameter pages, not within these two CRM setup pages. |
| **`custom_data` fields beyond `lead_event_source` and `event_source`** (e.g. `ad_id`, `campaign_name`, `stage`, `call_outcome`, `qualification_outcome_id`) | **UNVERIFIED** | The official CRM integration guide specifies only `lead_event_source` and `event_source: "crm"` inside `custom_data`. Any additional metadata fields passed for internal routing or attribution are unverified by these two official reference pages. |
