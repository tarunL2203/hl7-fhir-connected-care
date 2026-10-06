# Speaking script

## Slide 1: From FHIR records to useful answers

About 20 seconds. Say: This project turns synthetic healthcare records into three useful analytics reports. We used a saved two-patient batch to demonstrate resource completeness, a glucose timeline, and information availability before appointments. Today’s analytics milestone is complete. These reports show whether expected information is present; they do not make a clinical decision.

## Slide 2: How the data reaches the reports

About 30 seconds. Say: Earlier work established the HL7-to-FHIR application flow, AWS RDS storage, and an authenticated viewer. We exported a synthetic cohort and stored the files privately in S3. For this milestone, we loaded the saved export into Snowflake through an internal stage. Today we created typed Patient, Observation, and Appointment tables while retaining the source JSON and batch provenance, then built the three reports. The current analytics demonstration uses a saved batch rather than a live feed.

## Slide 3: Report 1  |  Is the cohort complete?

About 25 seconds. Say: This first report checks whether the expected resource types are present for each patient. Ravi has two observations and one appointment. Person02 has one observation and one appointment. Person02’s birth date is missing, and the report keeps that visible rather than filling it in. Both patients have the three resource types, but that does not mean every field is complete. If showing Snowflake, run only Report 1 and point to the two rows.

## Slide 4: Report 2  |  What is the glucose timeline?

About 25 seconds. Say: The second report links glucose observations to the right patient and orders them by measurement time. Ravi has readings of 95 and 102 milligrams per deciliter, both on October 1, one hour apart. Person02 has a reading of 95 on October 5. All three are final results. We retain the original timestamps and display a common UTC time for comparison. I am explaining the data timeline, not interpreting the values clinically. If showing Snowflake, run only Report 2.

## Slide 5: Report 3  |  Is expected information available?

About 35 seconds. Say: For this demonstration, we configured two appointments to require a qualifying glucose result in the previous seven days. The window includes the seven-day starting point and excludes the appointment time itself. Valid final, amended, or corrected glucose observations can qualify. Ravi has two qualifying results; Person02 has one. Both appointments therefore show information_complete. This is information availability under our configured demo rule, not a statement that a patient is medically cleared or that every clinical requirement is satisfied. If showing Snowflake, run only Report 3.

## Slide 6: Why the result is reproducible

About 30 seconds. Say: We retained the source JSON and provenance so the typed data can be traced to the saved batch. The typed tables contain two patients, three observations, and two appointments. Repeating each insert-only merge produced zero new rows: Observation and Appointment are supported by exported query history, and the Patient repeat was confirmed during the walkthrough. Nine focused SQL rule scenarios passed, including window boundaries, status filtering, and equivalent time zones. These checks support this bounded demonstration; they are not a complete production test suite.

## Slide 7: Next phase  |  Scale and automate

About 25 seconds. Say: The next phase is to automate the S3-to-Snowflake path, add more batches and resource types, and strengthen operational monitoring and least-privilege access. The automated S3 route is planned work. Its AWS role authorization still needs resolution before we enable it. Today’s completed demonstration uses the internal-stage route. We can now show the SQL, the actual exported results, and the checks as a reviewable analytics milestone. Thank you.