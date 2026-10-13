"""Read-only dashboard for Streamlit in Snowflake (warehouse runtime).

Create an app with FIRELY_DEMO_WH and paste this entire file into its editor.
The owner's role needs SELECT on the existing tables/views below. No AWS link,
external credentials, extra Python packages or Cortex calls are required.
"""
import json
import streamlit as st
from snowflake.snowpark.context import get_active_session

SCHEMA = "CHATGPT_LAB.FIRELY_RAW_5DD08717"
BRIDGE_BATCH = "hl7-appointment-bridge-20261007T162957465413Z"
FC30_BATCH = "synthetic-failure-cases-20261006-v1"

BRIDGE_REPORT_SQL = f"""
WITH a AS (
 SELECT batch_id, resource_id AS appointment_id,
   CASE WHEN REGEXP_LIKE(payload:participant[0]:actor:reference::VARCHAR,
      '(http://localhost:8080/)?Patient/[A-Za-z0-9.-]{{1,64}}')
      THEN SPLIT_PART(payload:participant[0]:actor:reference::VARCHAR, '/', -1)
   END AS patient_id,
   payload:status::VARCHAR AS appointment_status,
   payload:serviceType[0]:coding[0]:system::VARCHAR AS service_system,
   payload:serviceType[0]:coding[0]:code::VARCHAR AS service_code,
   TRY_TO_TIMESTAMP_TZ(payload:start::VARCHAR, 'AUTO') AS start_time,
   TRY_TO_TIMESTAMP_TZ(payload:end::VARCHAR, 'AUTO') AS end_time
 FROM {SCHEMA}.FHIR_RESOURCE_HL7_APPT_BRIDGE
 WHERE batch_id = '{BRIDGE_BATCH}' AND resource_type = 'Appointment'
), o AS (
 SELECT batch_id, resource_id AS observation_id, payload,
   CASE WHEN REGEXP_LIKE(payload:subject:reference::VARCHAR,
      '(http://localhost:8080/)?Patient/[A-Za-z0-9.-]{{1,64}}')
      THEN SPLIT_PART(payload:subject:reference::VARCHAR, '/', -1)
   END AS patient_id,
   TRY_TO_TIMESTAMP_TZ(payload:effectiveDateTime::VARCHAR, 'AUTO') AS measured_at
 FROM {SCHEMA}.FHIR_RESOURCE_HL7_APPT_BRIDGE
 WHERE batch_id = '{BRIDGE_BATCH}' AND resource_type = 'Observation'
), counts AS (
 SELECT a.*, p.resource_id AS resolved_patient_id,
   COALESCE(COUNT_IF(o.observation_id IS NOT NULL AND o.measured_at IS NULL), 0)
      AS invalid_time_count,
   COALESCE(COUNT_IF(
     o.payload:code:coding[0]:system::VARCHAR = 'http://loinc.org'
     AND o.payload:code:coding[0]:code::VARCHAR = '2345-7'
     AND o.payload:valueQuantity:system::VARCHAR = 'http://unitsofmeasure.org'
     AND o.payload:valueQuantity:code::VARCHAR = 'mg/dL'
     AND TRY_TO_DECIMAL(o.payload:valueQuantity:value::VARCHAR, 18, 6) IS NOT NULL
     AND o.payload:status::VARCHAR IN ('final','amended','corrected')
     AND o.measured_at >= DATEADD('day', -7, a.start_time)
     AND o.measured_at < a.start_time), 0) AS qualifying_glucose_count
 FROM a
 LEFT JOIN {SCHEMA}.FHIR_RESOURCE_HL7_APPT_BRIDGE p
   ON p.batch_id = a.batch_id AND p.resource_type = 'Patient'
  AND p.resource_id = a.patient_id
 LEFT JOIN o ON o.batch_id = a.batch_id AND o.patient_id = a.patient_id
 GROUP BY a.batch_id, a.appointment_id, a.patient_id, a.appointment_status,
   a.service_system, a.service_code, a.start_time, a.end_time, p.resource_id
)
SELECT patient_id, appointment_id, appointment_status, start_time,
 qualifying_glucose_count,
 CASE
   WHEN appointment_status = 'cancelled' THEN 'not_applicable'
   WHEN service_system IS NULL OR service_code IS NULL
     OR service_system <> 'https://example.org/synthetic-visit-types'
     OR service_code <> 'demo-glucose-review' THEN 'requirements_not_configured'
   WHEN resolved_patient_id IS NULL OR start_time IS NULL OR end_time IS NULL
     OR end_time <= start_time OR invalid_time_count > 0 THEN 'unable_to_assess'
   WHEN qualifying_glucose_count > 0 THEN 'information_complete'
   ELSE 'information_gap'
 END AS information_availability
FROM counts
"""

BRIDGE_RESOURCES_SQL = f"""
SELECT resource_type, resource_id, source_filename, file_row_number,
       loaded_at, TO_JSON(payload) AS payload_json
FROM {SCHEMA}.FHIR_RESOURCE_HL7_APPT_BRIDGE
WHERE batch_id = '{BRIDGE_BATCH}'
ORDER BY resource_type, resource_id
"""

FC30_REPORT_SQL = f"""
SELECT r.patient_id, p.given_name, p.family_name, p.birth_date_status,
 r.appointment_id, r.appointment_status, r.start_time,
 r.qualifying_glucose_count, r.information_availability
FROM {SCHEMA}.APPOINTMENT_FC30_REPORT r
LEFT JOIN {SCHEMA}.PATIENT_FC30_TYPED p
 ON p.batch_id = r.batch_id AND p.patient_id = r.patient_id
WHERE r.batch_id = '{FC30_BATCH}'
ORDER BY r.patient_id
"""

FC30_COUNTS_SQL = f"""
SELECT resource_type, COUNT(*) AS records,
       COUNT(DISTINCT resource_id) AS distinct_ids
FROM {SCHEMA}.FHIR_RESOURCE_FC30
WHERE batch_id = '{FC30_BATCH}'
GROUP BY resource_type ORDER BY resource_type
"""

FC30_REVIEW_SQL = f"""
SELECT o.observation_id, o.patient_reference_raw, o.effective_time_raw,
 CASE WHEN p.patient_id IS NULL AND o.effective_time IS NULL
        THEN 'unresolved_patient_and_invalid_time'
      WHEN p.patient_id IS NULL THEN 'unresolved_patient_reference'
      ELSE 'invalid_or_missing_timestamp' END AS review_reason
FROM {SCHEMA}.OBSERVATION_FC30_TYPED o
LEFT JOIN {SCHEMA}.PATIENT_FC30_TYPED p
 ON p.batch_id = o.batch_id AND p.patient_id = o.patient_id
WHERE o.batch_id = '{FC30_BATCH}'
 AND (p.patient_id IS NULL OR o.effective_time IS NULL)
ORDER BY o.observation_id
"""


@st.cache_data(ttl=60, show_spinner=False)
def query(sql):
    return get_active_session().sql(sql).to_pandas()


def table_and_download(frame, filename, key):
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        "Download this report",
        frame.to_csv(index=False),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def metrics(counts):
    values = dict(zip(counts["RESOURCE_TYPE"], counts["RECORDS"]))
    for column, name in zip(st.columns(3), ["Patient", "Observation", "Appointment"]):
        column.metric(name + " records", int(values.get(name, 0)))


def main():
    st.set_page_config(page_title="Firely information availability", layout="wide")
    st.title("Healthcare information availability")
    st.caption(
        "Synthetic training data. Results describe information availability for a configured demo rule."
    )
    source = st.sidebar.radio("Dataset", ["Verified HL7 sample", "30-patient failure cases"])
    if st.sidebar.button("Refresh reports"):
        query.clear()
    st.sidebar.caption("Reports refresh from Snowflake. Cached results expire after 60 seconds.")
    try:
        if source == "Verified HL7 sample":
            bridge()
        else:
            failure_cases()
    except Exception as error:
        st.error("The dashboard could not read an existing Snowflake object.")
        st.write(
            "Check that the app's owner role can read the listed schema and that the selected warehouse is available."
        )
        st.code(str(error))


def bridge():
    st.subheader("HL7 patient, labs and appointment")
    st.write(
        "This sample passed conversion-to-Firely comparison and full-payload reconciliation after an internal-stage load."
    )
    st.caption("Batch: " + BRIDGE_BATCH)
    resources = query(BRIDGE_RESOURCES_SQL)
    counts = resources.groupby("RESOURCE_TYPE", as_index=False).agg(RECORDS=("RESOURCE_ID", "size"))
    metrics(counts)
    appointment_tab, lab_tab, evidence_tab = st.tabs(
        ["Appointment report", "Glucose timeline", "Resource evidence"]
    )
    with appointment_tab:
        report = query(BRIDGE_REPORT_SQL)
        table_and_download(report, "hl7-appointment-report.csv", "bridge-report")
        st.caption(
            "Rule: numeric LOINC 2345-7, UCUM mg/dL, final/amended/corrected, from seven days before the appointment up to but excluding its start."
        )
        with st.expander("View the report SQL"):
            st.code(BRIDGE_REPORT_SQL, language="sql")
    with lab_tab:
        sql = f"""SELECT resource_id AS observation_id,
          payload:valueQuantity:value::NUMBER(18,6) AS glucose_mg_dl,
          payload:status::VARCHAR AS result_status,
          TRY_TO_TIMESTAMP_TZ(payload:effectiveDateTime::VARCHAR, 'AUTO') AS measured_at
        FROM {SCHEMA}.FHIR_RESOURCE_HL7_APPT_BRIDGE
        WHERE batch_id = '{BRIDGE_BATCH}' AND resource_type = 'Observation'
          AND payload:code:coding[0]:system::VARCHAR = 'http://loinc.org'
          AND payload:code:coding[0]:code::VARCHAR = '2345-7'
          AND payload:valueQuantity:system::VARCHAR = 'http://unitsofmeasure.org'
          AND payload:valueQuantity:code::VARCHAR = 'mg/dL'
        ORDER BY measured_at"""
        timeline = query(sql)
        table_and_download(timeline, "hl7-glucose-timeline.csv", "bridge-labs")
        if not timeline.empty:
            st.line_chart(timeline.set_index("MEASURED_AT")[["GLUCOSE_MG_DL"]])
    with evidence_tab:
        st.dataframe(
            resources.drop(columns=["PAYLOAD_JSON"]), use_container_width=True, hide_index=True
        )
        options = (resources["RESOURCE_TYPE"] + "/" + resources["RESOURCE_ID"]).tolist()
        if options:
            selected = st.selectbox("Inspect a loaded resource", options)
            index = options.index(selected)
            st.json(json.loads(resources.iloc[index]["PAYLOAD_JSON"]))
        st.caption(
            "The source manifest and HL7 files remain in the local export package. This dashboard reads the loaded batch; it does not rerun ingestion or the local comparison."
        )


def failure_cases():
    st.subheader("Synthetic failure-case analytics")
    st.write(
        "This separate dataset starts as FHIR JSON. It has not passed through the HL7 converters or Firely."
    )
    st.caption("Batch: " + FC30_BATCH)
    counts = query(FC30_COUNTS_SQL)
    metrics(counts)
    report = query(FC30_REPORT_SQL)
    review = query(FC30_REVIEW_SQL)
    if not review.empty:
        st.warning(
            "This batch has records requiring review. Appointment results remain an analytics preview while patient references are unresolved."
        )
    summary_tab, patient_tab, quality_tab = st.tabs(
        ["Appointment summary", "Patient details", "Data-quality review"]
    )
    with summary_tab:
        summary = (
            report.groupby("INFORMATION_AVAILABILITY").size().rename("APPOINTMENTS").to_frame()
        )
        st.bar_chart(summary)
        st.dataframe(summary.reset_index(), use_container_width=True, hide_index=True)
        table_and_download(report, "failure-case-appointment-report.csv", "fc30-full")
    with patient_tab:
        statuses = sorted(report["INFORMATION_AVAILABILITY"].dropna().unique().tolist())
        chosen = st.multiselect("Information availability", statuses, default=statuses)
        patient = st.text_input("Patient ID contains", placeholder="For example: fc30-p009")
        filtered = report[report["INFORMATION_AVAILABILITY"].isin(chosen)]
        if patient:
            filtered = filtered[filtered["PATIENT_ID"].str.contains(patient, regex=False, na=False)]
        table_and_download(filtered, "filtered-patient-report.csv", "fc30-filtered")
    with quality_tab:
        st.metric("Observation records requiring review", len(review))
        table_and_download(review, "observation-review-queue.csv", "fc30-review")
        birth = report[["PATIENT_ID", "BIRTH_DATE_STATUS"]].drop_duplicates()
        missing = birth[birth["BIRTH_DATE_STATUS"] == "missing"]
        st.metric("Patients with missing birth dates", len(missing))
        st.dataframe(missing, use_container_width=True, hide_index=True)
        st.caption(
            "Unresolved observations retain their original references. The dashboard does not assign them to an assumed patient or change records."
        )


if __name__ == "__main__":
    main()
