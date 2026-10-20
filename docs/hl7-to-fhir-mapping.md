# HL7 v2 → FHIR R4 mapping specification

The field-level mappings implemented by the three converters, written the way an interface specification would be. Each converter supports one deliberately bounded message shape and **rejects** anything else instead of guessing. HL7 v2 is parsed with [hl7apy](https://github.com/crs4/hl7apy) for ADT and ORU, and by a strict pipe-delimited parser for SIU.

| Message | Converter | FHIR resource | Sample input → output |
|---|---|---|---|
| ADT^A01 (admit) | [`convert_admission.py`](../converters/convert_admission.py) | Patient | [`admission-002.hl7`](../samples/admission-002.hl7) → [`.fhir.json`](../samples/admission-002.fhir.json) |
| ORU^R01 (lab result) | [`convert_lab.py`](../converters/convert_lab.py) | Observation | [`lab-002.hl7`](../samples/lab-002.hl7) → [`.fhir.json`](../samples/lab-002.fhir.json) |
| SIU^S12 (new booking) | [`appointment_bridge.py`](../converters/appointment_bridge.py) | Appointment | [`appointment-bridge-001.hl7`](../samples/appointment-bridge-001.hl7) → [`.fhir.json`](../samples/appointment-bridge-001.fhir.json) |

## ADT^A01 → Patient

| HL7 v2 field | Rule | FHIR element |
|---|---|---|
| MSH-9 | Must be `ADT^A01^ADT_A01` | (gate) |
| PID-3.4 assigning authority | Must be `DEMO` | (gate) |
| PID-3.1 ID number (MRN) | Required | `identifier[0].value`, with `identifier[0].system` = `https://example.org/training/mrn` |
| PID-5.1 family name | Required | `name[0].family` |
| PID-5.2 given name | Required | `name[0].given[0]` |
| PID-7 date of birth (`YYYYMMDD`) | Parsed as a date | `birthDate` (`YYYY-MM-DD`) |
| PID-8 administrative sex | `M`/`F`/`O`/`U` → `male`/`female`/`other`/`unknown` | `gender` |
| EVN, PV1 | Not mapped (Encounter is out of scope) | – |

**Identity.** The converter first searches Firely for `Patient?identifier=<system>|<MRN>`:
- More than one match: rejected as a duplicate identifier, for manual review.
- One match: the existing Patient ID is reused.
- No match: the ID is derived as `patient-` + UUID5(`<system>|<MRN>`), so the same patient always gets the same ID.

Names are never used for matching.

## ORU^R01 → Observation

| HL7 v2 field | Rule | FHIR element |
|---|---|---|
| MSH-9 | Must be `ORU^R01^ORU_R01` | (gate) |
| OBX segments | Exactly one | (gate) |
| PID-3.4 / PID-3.1 | Looked up in the converter's `PATIENT_INDEX`, (`DEMO`, `SYN002`) → `demo-patient-002`; unknown patients are rejected | `subject.reference` = `Patient/<id>` |
| OBX-2 value type | Must be `NM` (numeric) | (gate) |
| OBX-11 result status | Must be `F` (final) | `status` = `final` |
| OBX-3 observation identifier | Coding system (component 3) must be `LN` | `code.coding[0]`: `system` = `http://loinc.org`, `code` = OBX-3.1, `display` = OBX-3.2 |
| OBX-5 value | Must parse to a finite number | `valueQuantity.value` |
| OBX-6 units | Coding system (component 3) must be `UCUM` | `valueQuantity.unit` and `.code` = OBX-6.1, `.system` = `http://unitsofmeasure.org` |
| OBR-7 observation date/time | Must include seconds and a UTC offset | `effectiveDateTime` (ISO 8601 with offset) |
| (fixed) | – | `category` = `laboratory` (observation-category code system) |

**Identity.** The ID is `lab-` + UUID5 over the source key [MSH-3 sender, MSH-4 facility, PID-3.4 authority, PID-3.1 MRN, OBR-3.2 order authority, OBR-3.1 order ID, OBX-1 set ID]. All seven parts are required. Replaying the same result therefore always produces the same resource, while a different order or result number produces a new one. The original demo result keeps its earlier ID, `demo-glucose-002`, through the `LEGACY_RESULT_IDS` table.

## SIU^S12 → Appointment

| HL7 v2 field | Rule | FHIR element |
|---|---|---|
| Segment structure | Exactly `MSH`, `SCH`, `PID`, `RGS`, `AIS`; no repeating fields or escape sequences | (gate) |
| MSH-9 / MSH-12 | `SIU^S12^SIU_S12`, version `2.5.1` | (gate) |
| MSH-3 / MSH-4 / MSH-11 | Synthetic sender `DEMO` / `TRAINING`, processing ID `T` | (gate) |
| PID-3 | Must be `SYN002^^^DEMO^MR`; the identifier must resolve to exactly one Patient in Firely | `participant[0].actor.reference` = `Patient/<id>`, `participant[0].status` = `accepted` |
| SCH-25 filler status | Must be `Booked` | `status` = `booked` |
| SCH-11 timing (TQ) | Component 4 = start, component 5 = end; seconds and a UTC offset required; end after start | `start`, `end` |
| SCH-9 / SCH-10 duration | Must equal the SCH-11 interval (30 min) | `minutesDuration` = 30 |
| SCH-7 reason, AIS-3 service | Must agree (`demo-glucose-review`) | `serviceType[0].coding[0]` (synthetic visit-type code system) |
| AIS-4 / AIS-7 / AIS-8 | Start and duration must agree with SCH | (consistency check) |
| SCH-2 filler appointment ID (EI) | ID and authority (`DEMO`) both required | `identifier[0]` (system `https://example.org/training/appointment`) |
| (fixed) | – | `meta.tag` = `synthetic`, `description` = "Synthetic glucose review" |

**Identity.** The ID is `siu-appointment-` + UUID5 over [MSH-3, MSH-4, SCH-2.1, SCH-2.2]. The bridge writes the Appointment to Firely with an idempotent `PUT` on that ID, then reads it back and compares it with the conversion before exporting anything. An offline self-test covers the mapping, stable IDs, timestamps and references: `python converters/appointment_bridge.py --self-test`.

## Rejections at a glance

Every converter fails closed, raising an error that names the problem rather than producing a partial resource. [`converters/test_converters.py`](../converters/test_converters.py) runs these cases in CI:

- Unsupported message type, version, sender or segment structure.
- An identifier authority or patient outside the configured mapping, or a duplicate identifier match.
- Missing required fields: MRN, names, order and result identifiers.
- A non-numeric, non-final or non-finite lab value; a non-LOINC code; non-UCUM units.
- A timestamp without seconds or a UTC offset; an appointment that ends before it starts; durations that disagree.

## From these mappings to production

A production interface would add:
- An enterprise master patient index in place of the single-authority rule.
- Mapping tables for local codes and units to LOINC and UCUM, with unit conversion.
- Repeating OBX groups and ORC/OBR order context.
- Message acknowledgements (ACK/NAK) and replay from an interface engine.
- Additional SIU events (S13 reschedule, S15 cancel), mapped to Appointment updates under the policy's correction and cancellation rules.

---

<sub>**Reading order 7 of 12** · ← [Decisions](decisions.md) · [Snowflake design](snowflake-design.md) → · [README](../README.md)</sub>
