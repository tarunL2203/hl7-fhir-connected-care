# Speaking notes for the current demonstration

## Purpose
“I am demonstrating how a small set of synthetic healthcare messages reaches queryable data in Snowflake. The patient, lab and appointment examples all have a source message. I can trace the exported resource IDs back to those files.”

## Conversion and Firely
“The admission converter maps selected patient demographics, the lab converter maps two final glucose measurements, and the scheduling sample produces one booked appointment. We checked the resource fields against local Firely before export. We also reconciled a missing gender field and recognized that relative and absolute references can identify the same local patient.”

## Snowflake proof
“The final batch contains one patient, two observations and one appointment. We uploaded its resource files through a Snowflake internal stage. Our local reconciliation compared the complete loaded JSON payloads and their source-file row positions with the Firely export. All four matched.”

## Appointment query
“The demo rule asks whether qualifying glucose information is available in the seven days before the appointment. The two measurements are 95 and 102 mg/dL. The appointment starts October 6 at 13:00 UTC. The query should count both. I will show the actual result before describing the assessment as verified. This rule measures information availability, not clinical readiness.”

## Failure-case analytics
“A separate synthetic FHIR dataset tests analytics under missing data and business failure conditions. It contains 30 patients and 30 appointments, with 87 observations. The report distinguishes complete information, gaps, cancelled appointments, missing configuration and cases that cannot be assessed. That dataset has not gone through the HL7 conversion path. Four observation references remain unresolved and require review.”

## Scaling
“The current integration uses manual internal-stage delivery. A later phase can automate the existing private S3 route and extend message coverage. The bridge already works without that direct connection.”
