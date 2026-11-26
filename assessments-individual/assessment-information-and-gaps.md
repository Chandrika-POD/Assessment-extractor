# Assessment information and missing data

Date: 26 November 2026. Coverage: 186 individual assessment JSON exports.

The exports contain questions, draft scoring rules and report specifications that can support an assessment application. Availability varies by assessment. A populated configuration is not proof that its calculations, chart mappings or report layout have been validated.

## Available information

| Information | Available |
| --- | --- |
| Questions and answer options | 4,927 questions across **185 assessments**; SDQ questions are missing. |
| Scoring formulas | **729 draft rules** across **183 assessments**. |
| Graph and plot specifications | **346 charts** across **174 assessments**, including types, axes, colours, labels and series. Some bindings and parameters remain unresolved. |
| Report tables | **793 tables** across **184 assessments**. Table contents and bindings still require review. |
| Report structure | Pages and sections in **185 assessments**; theme and interpretation configuration objects in **186**. Interpretation guidance is not equivalent to executable interpretation rules. |

Chart and table counts refer to the dedicated `report_configuration.charts` and `report_configuration.tables` arrays. The older `reporting` configuration is separate and is not included in those counts. Missing dedicated charts or tables does not establish that a source report should contain them.

## Assessments with absent information

### Missing questionnaire

- **Strengths and Difficulties Questionnaire (SDQ):** no questionnaire items or answer options are included. Its export also has no executable numeric scoring rules. The recorded requirements are an authorized digital form and the appropriate respondent and age variant. Report chart and table specifications are present, but they do not supply the missing questionnaire.

### Assessments without numeric scoring rules

| Assessment | What the export supports |
| --- | --- |
| Strengths and Difficulties Questionnaire (SDQ) | Unavailable mode; questionnaire and numeric rules are absent. |
| Ask Suicide-Screening Questionnaire (asQ) | Screening protocol mode. A numeric composite is not provided; absence of a sum rule is not automatically an extraction defect. |
| Life Events Checklist for DSM-5 (LEC-5) | Descriptive response mode. Responses are recorded without a numeric composite. |

### Assessments without dedicated chart entries

The following 12 exports have an empty dedicated charts array. This can reflect a table or text report, or an alternative layout; it does not mean their questions or scoring rules are absent.

- Automatic Thoughts Questionnaire – Believability (ATQ-B)
- Client Satisfaction Survey (CSS)
- Eating Attitudes Test-26 (EAT-26)
- Leeds Dependence Questionnaire (LDQ)
- Life Events Checklist for DSM-5 (LEC-5)
- Multilevel Assessment of Psychopathology (MAPsy)
- Opioid Risk Tool (ORT)
- Scale of Positive and Negative Experience (SPANE)
- Session Reactions Scale – 3 – Brief (SRS-3-B)
- Short Health Anxiety Inventory (SHAI)
- Tampa Scale of Kinesiophobia (TSK)
- Your Experience of Service (YES)

### Assessments without dedicated table entries

- Multilevel Assessment of Psychopathology (MAPsy)
- Panic Disorder Severity Scale (PDSS)

### Assessment without standard report pages and sections

**Multilevel Assessment of Psychopathology (MAPsy)** has no entries in the standard pages, sections, charts or tables arrays. It has a separate `interactiveLayout` with sections and a source contract. Its exceptions record missing full percentile lookup tables and incomplete hierarchical rendering, PDF export, patient tables, narratives, chart bindings and first-versus-repeat validation. Sample result payloads are not a scoring algorithm.

## Information that remains incomplete or unreviewed

| Area | Current status |
| --- | --- |
| Clinical approval and application readiness | All 186 dedicated configurations mark clinical approval, application import readiness and renderer equivalence as false. |
| Enabled scoring and charts | None of the 186 top-level scoring configurations are enabled; all 346 dedicated charts have runtimeEnabled set to false. |
| Interpretation and repeat reports | All 186 record interpretation and variant rules requiring review. Only 11 have nonempty encoded interpretation rules; none have interpretation templates. The 11 are not thereby complete or approved. |
| Percentile calculation | No export contains entries in scoring.percentile_rules. This is not evidence that every instrument requires percentiles. Sixty-six explicitly flag incomplete normative conversions; MAPsy separately flags absent full lookup tables. |
| Score to chart mappings | 174 explicitly require score and series binding review; MAPsy has a separate binding review exception. |
| Unresolved chart series | 47 assessments explicitly flag unresolved chart series. They are marked C in the matrix below. |
| Reference distribution curves | Seven assessments explicitly require numeric curve parameters; marked D below. |
| Panel axes and series | Four assessments explicitly require per-panel bindings; marked A below. |
| Table meanings and bindings | All 184 exports with dedicated tables record table cell semantics requiring review. |
| Styling | 78 record paint style roles requiring review; marked S below. |
| Older dedicated profiles | Three retain older profiles that were not revalidated; marked L below. |

These statuses describe the exported data. They are not new clinical findings. Original verification metadata refers to source definitions, before the portable export cleanup.

## Assessment by assessment availability

Counts show entries present, not validated completeness. Every row remains subject to the shared review gaps above. A dash in the flags column means no additional listed flag; it does not mean production readiness. Duplicate assessment titles include their identifying suffix.

| Flag | Meaning |
| --- | --- |
| Q0 | No questionnaire items. |
| R0 | No numeric scoring rules; check the report mode described above. |
| G0 | No dedicated chart entries. |
| T0 | No dedicated table entries. |
| P0 | No standard report pages or sections. |
| C | Chart series explicitly unresolved. |
| N | Normative conversions explicitly incomplete. |
| D | Reference distribution curves need numeric parameters. |
| A | Individual panel axes and series need bindings. |
| S | Paint style roles need review. |
| L | Existing older dedicated profile was not revalidated. |
| M | MAPsy-specific implementation and lookup-table gaps described above. |

| Assessment | Questions | Rules | Charts | Tables | Flags |
| --- | ---: | ---: | ---: | ---: | --- |
| Acceptance and Action Questionnaire – version 2 (AAQ-2) | 7 | 1 | 1 | 1 | N |
| ADHD Clinical Outcome Scale (ACOS-Clinician) – Clinician Version | 15 | 1 | 2 | 5 | — |
| ADHD Clinical Outcome Scale (ACOS-Self) – Self-Report Version | 15 | 1 | 2 | 4 | — |
| Adolescent Dissociative Experiences Scale (A-DES) | 30 | 5 | 2 | 4 | C, D |
| Adult ADHD Observer-Report Scale (ASRS-O) | 18 | 5 | 2 | 3 | S |
| Adult ADHD Self-Report Scale (ASRS) | 18 | 3 | 2 | 2 | S |
| Adult Separation Anxiety Questionnaire (ASA-27) | 27 | 1 | 2 | 3 | C, S |
| Adverse Childhood Experiences Questionnaire (ACE-Q) | 10 | 1 | 1 | 3 | S |
| Agnew Relationship Measure – 5 (ARM-5) | 5 | 1 | 2 | 2 | S |
| Alcohol Use Disorders Identification Test (AUDIT) | 12 | 1 | 3 | 4 | C, S |
| Alexian Brothers Urge to Self-Injure Scale (ABUSI) | 5 | 1 | 1 | 1 | C |
| Anxiety, Depression, and Mood Scale (ADAMS) | 28 | 5 | 1 | 4 | — |
| Appearance Anxiety Inventory (AAI) | 10 | 4 | 2 | 3 | C, S |
| Ask Suicide-Screening Questionnaire (asQ) | 8 | 0 | 1 | 1 | R0 |
| Athens Insomnia Scale (AIS) | 8 | 3 | 2 | 2 | S, L |
| Athlete Psychological Strain Questionnaire (APSQ) | 10 | 1 | 1 | 4 | S |
| Athletic Coping Skills Inventory (ACSI-28) | 28 | 8 | 1 | 5 | N |
| Attachment Style Questionnaire – Short Form (ASQ-SF) | 29 | 7 | 1 | 6 | C |
| Autism Spectrum Quotient (AQ) | 50 | 1 | 3 | 4 | C, N, A |
| Autism Spectrum Quotient Adolescent Version (AQ-Adolescent) | 50 | 1 | 3 | 5 | C, N, A |
| Autism Spectrum Quotient Children’s Version (AQ-Child) | 50 | 1 | 3 | 6 | C, N, A |
| Autism Treatment Evaluation Checklist (ATEC) | 77 | 5 | 2 | 7 | — |
| Automatic Thoughts Questionnaire – Believability (ATQ-B) | 15 | 1 | 0 | 2 | G0 |
| Benevolent Childhood Experiences (BCEs) scale | 20 | 3 | 1 | 3 | N |
| Binge-Eating Scale (BES) | 16 | 1 | 2 | 1 | C |
| Borderline Symptom List (BSL-23) | 24 | 1 | 2 | 5 | — |
| Brief 2-Way Social Support Scale (Brief 2-Way SSS) | 12 | 1 | 1 | 5 | S |
| Brief Addiction Monitor – Continuous (BAM) | 23 | 3 | 10 | 8 | S |
| Brief Early Schema Questionnaire (BESQ) | 24 | 5 | 2 | 7 | — |
| Brief Emotional Distress Scale for Youth (BEDSY) | 8 | 1 | 1 | 3 | N |
| Brief Emotional Intelligence Scale (BEIS-10) | 10 | 1 | 1 | 2 | N |
| Brief Experiential Avoidance Questionnaire (BEAQ) | 15 | 1 | 2 | 1 | C, N |
| Brief Hierarchical Taxonomy of Psychopathology (B-HiTOP) | 45 | 8 | 9 | 6 | C |
| Brief Resilience Scale (BRS) | 6 | 1 | 1 | 1 | N, S |
| Buss and Perry Aggression Questionnaire (BPAQ) | 29 | 1 | 1 | 5 | N |
| Camouflaging Autistic Traits Questionnaire (CAT-Q) | 25 | 1 | 5 | 4 | C, N |
| Center for Epidemiologic Studies Depression Scale – Revised (CESD-R) | 20 | 1 | 1 | 3 | C, S |
| Center for Epidemiological Studies Depression Scale for Children (CES-DC) | 20 | 1 | 3 | 4 | N |
| Child Dissociative Checklist (CDC) | 20 | 1 | 2 | 3 | C, D |
| Childhood Autism Spectrum Test (CAST) | 44 | 1 | 2 | 4 | C |
| Children’s Eating Attitudes Test (ChEAT) | 26 | 5 | 1 | 4 | — |
| Client Satisfaction Survey (CSS) | 10 | 1 | 0 | 2 | G0 |
| Clinical Impairment Assessment Questionnaire (CIA) | 16 | 1 | 1 | 4 | N, S |
| Clinical Outcomes in Routine Evaluation (CORE-OM) | 34 | 5 | 2 | 5 | N, S |
| Clinical Outcomes in Routine Evaluation 10 (CORE-10) | 10 | 1 | 2 | 3 | C, S |
| Cognitive Flexibility Inventory (CFI) | 20 | 3 | 1 | 3 | S |
| Compassion Motivation and Action Scale – Self-Compassion (CMAS-Self) | 18 | 1 | 2 | 8 | N, S |
| Compassion Motivation and Action Scales – Compassion (CMAS-other) | 12 | 1 | 1 | 3 | N, S |
| Composite Caregiving Questionnaire (CCQ) | 45 | 5 | 1 | 7 | N |
| Comprehensive Autistic Trait Inventory (CATI) | 42 | 1 | 3 | 4 | C, N, A |
| Coping Orientation to Problems Experienced Inventory (Brief-COPE) | 28 | 3 | 3 | 7 | C, N, S |
| Counselling Self Estimate Inventory (COSE) | 37 | 6 | 1 | 5 | S |
| Couples Satisfaction Index (CSI-16) | 16 | 1 | 1 | 2 | S |
| CRAFFT Substance Use Assessment (CRAFFT 2.1+N) | 20 | 2 | 2 | 5 | — |
| Death Anxiety Beliefs and Behaviours Scale (DABBS) | 18 | 1 | 1 | 5 | C, N, S |
| Depression Anxiety Stress Scale (DASS-10) | 12 | 6 | 4 | 6 | S |
| Depression Anxiety Stress Scales – Long Form (DASS-42) | 42 | 4 | 1 | 5 | N, S |
| Depression Anxiety Stress Scales – Short Form (DASS-21) | 21 | 7 | 2 | 3 | N, L |
| Depression Anxiety Stress Scales – Youth Version (DASS-Y) | 21 | 4 | 2 | 3 | N |
| Difficulties in Emotion Regulation Scale (DERS) | 36 | 1 | 2 | 4 | N |
| Difficulties in Emotion Regulation Scale – 16 item version (DERS-16) | 16 | 1 | 2 | 4 | N |
| Digital Stress Scale (DSS) | 24 | 6 | 1 | 4 | N, S |
| Dimensions of Anger Reactions (DAR-5) | 5 | 1 | 2 | 2 | — |
| Dissociative Experiences Scale – II (DES-II) | 28 | 3 | 3 | 6 | C, D |
| Drug Use Disorders Identification Test (DUDIT) | 11 | 1 | 1 | 3 | — |
| Eating Attitudes Test-26 (EAT-26) | 31 | 1 | 0 | 5 | G0 |
| Eating Disorder-15 (ED-15) | 15 | 1 | 7 | 3 | C |
| Edinburgh Postnatal Depression Scale (EPDS) | 10 | 1 | 1 | 2 | C |
| Empathy Quotient (EQ-40) | 40 | 1 | 3 | 4 | C, S |
| Equanimity Scale – 16 (ES-16) | 16 | 3 | 1 | 4 | N, S |
| Executive Skills Questionnaire – Revised (ESQ-R) | 25 | 1 | 2 | 3 | N |
| Experience in Close Relationship Scale – Short Form (ECR-S) | 12 | 2 | 1 | 6 | C |
| Extreme Demand Avoidance Questionnaire – Adult (EDA-QA) | 26 | 1 | 1 | 3 | — |
| Extreme Demand Avoidance – 8 (EDA-8) | 8 | 1 | 1 | 1 | C, S |
| Fatigue Assessment Scale (FAS) | 10 | 1 | 1 | 3 | — |
| Five Facet Mindfulness Questionnaire (FFMQ-15) | 15 | 6 | 1 | 5 | S |
| Flourishing Scale (FS) | 8 | 1 | 1 | 3 | — |
| Frost Multidimensional Perfectionism Scale (FMPS) | 35 | 5 | 1 | 5 | N, S |
| Gender Preoccupation and Stability Questionnaire 2 (GPSQ-2) | 17 | 1 | 2 | 4 | C, N, S |
| General Behaviour Inventory (GBI) | 73 | 4 | 5 | 7 | C, N |
| Generalised Anxiety Disorder Assessment (GAD-7) | 7 | 1 | 1 | 2 | S |
| Geriatric Depression Scale (GDS-15) | 15 | 1 | 2 | 4 | C, N |
| Herth Hope Index (HHI) | 12 | 1 | 2 | 2 | S |
| Indigenous Risk Impact Screen (IRIS) | 13 | 2 | 2 | 3 | S |
| Institute for Basic Research – Modified Overt Aggression Scale (IBR-MOAS) | 20 | 2 | 1 | 6 | — |
| International Personality Item Pool – NEO – 120 item version (IPIP-NEO-120) | 120 | 35 | 5 | 15 | S |
| International Trauma Questionnaire (ITQ) | 18 | 10 | 3 | 7 | N |
| International Trauma Questionnaire – Child and Adolescent Version (ITQ-CA) | 22 | 10 | 3 | 7 | N |
| Kessler Psychological Distress Scale PLUS (K10+) | 14 | 1 | 2 | 5 | N, S |
| Kessler Psychological Distress Scale-5 (K5) | 5 | 1 | 1 | 2 | — |
| Leadership Scale for Sports (LSS-15) | 15 | 6 | 1 | 3 | N, S |
| Leeds Dependence Questionnaire (LDQ) | 10 | 1 | 0 | 1 | G0 |
| Life Events Checklist for DSM-5 (LEC-5) | 17 | 0 | 0 | 4 | R0, G0 |
| Life Orientation Test Revised (LOT-R) | 10 | 1 | 1 | 1 | N, S |
| Life Skills Profile (LSP-16) | 16 | 1 | 1 | 4 | S |
| Maladaptive Schema Scale (MSS) | 108 | 27 | 3 | 8 | — |
| Maladaptive Schema Scale – Young Schema Aligned (MSS-YSQ) | 76 | 19 | 2 | 7 | — |
| Male Depression Risk Scale (MDRS-22) | 22 | 1 | 2 | 4 | S |
| Manic and Depression Symptoms Paired Screening (PMQ-9 and PHQ-9) | 18 | 2 | 3 | 5 | C |
| MASCC Unmet Needs Assessment for Cancer-Related Cognitive Impairment Impact (MASCC COG-IMPACT) | 110 | 16 | 2 | 14 | — |
| McLean Screening Instrument for BPD (MSI-BPD) | 10 | 1 | 1 | 3 | — |
| Menopause Depression Rating Scale (MENO-D) | 12 | 1 | 2 | 2 | S |
| Mental Health Literacy Scale (MHLS) | 35 | 1 | 3 | 4 | C |
| Mindfulness-Based Self Efficacy Scale – Revised (MSES-R) | 22 | 6 | 1 | 4 | N, S |
| Montgomery-Asberg Rating Scale (MADRS) | 10 | 1 | 1 | 2 | — |
| Mood and Feelings Questionnaire-Self Report (MFQ-Self) | 13 | 1 | 1 | 3 | — |
| Mood and Feelings Questionnaire: Parent Report (MFQ-Parent) | 13 | 1 | 1 | 4 | — |
| Mood Disorder Questionnaire (MDQ) | 15 | 1 | 2 | 3 | S |
| Multidimensional Assessment of Interoceptive Awareness – Version 2 (MAIA-2) | 37 | 8 | 1 | 5 | C, N, S |
| Multidimensional Assessment of Interoceptive Awareness – Youth Version (MAIA-Y) | 32 | 8 | 1 | 4 | N |
| Multidimensional Inventory of Dissociation – 60-item Adolescent version (MID-60-A) | 60 | 11 | 1 | 10 | S |
| Multidimensional Inventory of Dissociation – 60-item version (MID-60) | 60 | 11 | 3 | 6 | C, S |
| Multilevel Assessment of Psychopathology (MAPsy) | 155 | 1 | 0 | 0 | G0, T0, P0, M |
| NovoPsych Five Factor Personality Scale – 30 item version (NFFPS-30) | 30 | 35 | 1 | 13 | N |
| Obsessional Compulsive Inventory – Child Self Report (ChOCI-R-S) | 38 | 6 | 4 | 10 | — |
| Obsessional Compulsive Inventory- Revised-Parent (ChOCI-R-P) [295461a1825b] | 38 | 6 | 4 | 9 | — |
| Obsessional Compulsive Inventory- Revised-Parent (ChOCI-R-P) [fcfe218a4155] | 38 | 6 | 4 | 9 | — |
| Obsessive Compulsive Inventory – Revised (OCI-R) | 18 | 1 | 6 | 7 | C, N, S |
| Oldenburg Burnout Inventory (OLBI) | 16 | 3 | 2 | 2 | N, S |
| Opioid Risk Tool (ORT) | 10 | 1 | 0 | 2 | G0 |
| Pain Self-Efficacy Questionnaire (PSEQ) | 10 | 1 | 1 | 2 | — |
| Panic Disorder Severity Scale (PDSS) | 7 | 1 | 2 | 0 | T0, C |
| Patient Health Questionnaire – Depression (PHQ-9) | 9 | 1 | 2 | 2 | C |
| Pediatric Symptom Checklist-17 (PSC-17) | 17 | 1 | 4 | 5 | C |
| Penn Alcohol Craving Scale (PACS) | 5 | 1 | 2 | 1 | — |
| Penn State Worry Questionnaire (PSWQ) | 16 | 1 | 1 | 2 | C |
| Perfectionistic Cognitions Inventory (PCI) | 25 | 1 | 1 | 4 | S |
| Personal Wellbeing Index – Adult (PWI-A) | 9 | 1 | 1 | 2 | — |
| Personality Inventory for DSM-5 – Short Form (PID-5-SF) | 100 | 5 | 14 | 11 | N |
| Phobic Stimuli Response Scale (PSRS) | 46 | 1 | 1 | 5 | N |
| Pica, ARFID, and Rumination Disorder Interview – ARFID Questionnaire (PARDI-AR-Q) | 33 | 4 | 2 | 6 | C, S |
| Pica, ARFID, and Rumination Disorder Interview – ARFID Questionnaire: Informant-report (PARDI-AR-Q-Informant) | 33 | 4 | 2 | 5 | C, S |
| Positive and Negative Affect Schedule (PANAS) | 20 | 2 | 1 | 4 | N |
| Positive Childhood Experiences (PCEs) scale | 7 | 1 | 1 | 1 | — |
| Preschool Anxiety Scale (PAS) | 35 | 1 | 1 | 5 | N, S |
| Problem Gambling Severity Index (PGSI) | 9 | 1 | 1 | 2 | — |
| Protective Factors of Resilience Scale (PFRS) | 15 | 4 | 1 | 4 | S |
| PTSD Checklist for DSM-5 (PCL-5) | 20 | 1 | 2 | 4 | C, S |
| Reflective Practice Questionnaire – Extended (RPQ-E) | 30 | 4 | 1 | 5 | — |
| Regensburg Insomnia Scale (RIS) | 10 | 4 | 2 | 4 | N, S, L |
| Repetitive Behaviours Questionnaire–3 (RBQ-3) | 20 | 6 | 3 | 3 | C, S |
| Revised Child Anxiety and Depression Scale – Child (RCADS-Child) [1a892743a41c] | 47 | 8 | 1 | 4 | N |
| Revised Child Anxiety and Depression Scale – Child (RCADS-Child) [a7bbc1219098] | 47 | 8 | 1 | 4 | N |
| Revised Child Anxiety and Depression Scale – Parent (RCADS-Parent) | 47 | 8 | 1 | 5 | N |
| Ritvo Autism Asperger Diagnostic Scale – Revised (RAADS-R) | 80 | 9 | 3 | 7 | D |
| Rosenberg Self-Esteem Scale (RSES) | 10 | 1 | 2 | 2 | C, D, S |
| Ruminative Responses Scale (RRS) | 22 | 1 | 2 | 6 | C |
| Satisfaction with Life Scale (SWLS) | 5 | 1 | 1 | 2 | — |
| Scale of Positive and Negative Experience (SPANE) | 12 | 3 | 0 | 2 | G0 |
| Screen for Child Anxiety Related Emotional Disorders Child Version (SCARED Child) | 41 | 1 | 2 | 5 | N, S |
| Screen for Child Anxiety Related Emotional Disorders Parent Version (SCARED Parent) | 41 | 1 | 1 | 5 | — |
| Self-Compassion Scale – Short Form (SCS-SF) | 12 | 3 | 2 | 4 | D, S |
| Session Reactions Scale – 3 – Brief (SRS-3-B) | 15 | 4 | 0 | 3 | G0 |
| Short Health Anxiety Inventory (SHAI) | 18 | 1 | 0 | 3 | G0 |
| Social Avoidance and Distress Scale (SADS) | 28 | 1 | 1 | 2 | — |
| Spence Children’s Anxiety Scale – Child (SCAS-Child) | 46 | 7 | 1 | 5 | N, S |
| Spence Children’s Anxiety Scale – Parent (SCAS-Parent) | 39 | 6 | 1 | 5 | N, S |
| State Difficulties in Emotion Regulation Scale (S-DERS) | 21 | 5 | 2 | 3 | N, S |
| Strengths and Difficulties Questionnaire (SDQ) | 0 | 0 | 3 | 2 | Q0, R0 |
| Strengths and Stressors (SAS) | 35 | 6 | 1 | 4 | — |
| Supervisory Styles Inventory (SSI) | 25 | 3 | 1 | 5 | — |
| Tampa Scale of Kinesiophobia (TSK) | 17 | 1 | 0 | 2 | G0 |
| Team Psychological Safety (TPS-7) | 7 | 1 | 1 | 2 | N, S |
| The Impact of Event Scale – Revised (IES-R) | 22 | 1 | 2 | 4 | S |
| The Kessler Psychological Distress Scale (K10) | 10 | 1 | 2 | 3 | N, S |
| The Professional Quality of Life Scale – 5 (ProQOL) | 30 | 3 | 1 | 3 | C |
| The World Health Organisation Disability Assessment Schedule (WHODAS 2.0) – Self-Report Version | 39 | 7 | 1 | 5 | S |
| Thought Action Fusion Scale – Revised (TAFS-R) | 19 | 1 | 1 | 3 | N, S |
| Tinnitus Handicap Inventory (THI) | 25 | 1 | 1 | 4 | N, S |
| Toronto Alexithymia Scale (TAS) | 20 | 1 | 1 | 4 | N, S |
| Trauma Recovery Measure (TRM) | 15 | 1 | 2 | 4 | C, N |
| Valuing Questionnaire (VQ) | 10 | 2 | 1 | 1 | — |
| Vancouver Obsessional Compulsive Inventory (VOCI) | 55 | 1 | 7 | 7 | C |
| Vanderbilt ADHD Diagnostic Parent Rating Scale (VADPRS) | 55 | 13 | 2 | 7 | N, S |
| Vanderbilt ADHD Diagnostic Teacher Rating Scale (VADTRS) | 44 | 11 | 1 | 7 | N, S |
| Weiss Symptom Record II (WSR-II) | 123 | 57 | 1 | 9 | — |
| Wender Utah Rating Scale – 25 item version (WURS-25) | 25 | 4 | 5 | 6 | N, D, S |
| WHO – Quality of Life – Brief (WHOQOL-BREF) | 26 | 5 | 2 | 4 | N, S |
| Why Have Sex? Questionnaire Short Form (YSEX-SF) | 28 | 14 | 1 | 12 | — |
| Work and Social Adjustment Scale (WSAS) | 5 | 1 | 4 | 3 | — |
| World Health Organisation Disability Assessment Schedule 2.0 – Interview (WHODAS-interview) | 43 | 8 | 1 | 6 | S |
| World Health Organisation Disability Assessment Schedule 2.0 – Proxy (WHODAS-proxy) | 39 | 7 | 1 | 5 | S |
| World Health Organisation Disability Assessment Schedule – Children and Youth version (WHODAS-Child) | 40 | 13 | 1 | 5 | S |
| Young Person’s CORE (YP-CORE) | 10 | 1 | 1 | 4 | S |
| Your Experience of Service (YES) | 28 | 8 | 0 | 6 | G0 |
| Zung Self-Rating Depression Scale | 20 | 4 | 2 | 5 | — |

## Using the data in the existing application

The PHQ-9-assessment application already collects answers, calculates supported draft scores and prints basic reports. Its current report flow reads the older reporting configuration. Importing these files and rendering their dedicated report_configuration requires application changes. Once imported into the application database, the assessment data need not depend on the original export folder. Missing questionnaire content, norm formulas and unresolved bindings still require completion; importing the files does not resolve them.

Source: the 186 cleaned individual assessment JSON exports. Counts use questionnaire.items, scoring.rules and the dedicated report_configuration arrays. Additional flags use report_configuration.exceptions; shared readiness statuses use scoring and report_configuration.validation. No source JSON was modified to create this report.
