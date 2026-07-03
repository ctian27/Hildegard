"""
Disease-group and journal configuration for the heme/onc literature
surveillance pipeline.

Journal filter terms and ISSNs below were resolved live against the NCBI
E-utilities `esearch`/`esummary` endpoints (PubMed [Journal] field + NLM
Catalog) on 2026-07-01 -- see the pairing note in each JOURNALS block.
Re-verify periodically; PubMed's [Journal] field matches on ISO abbreviation
or exact full title, NOT arbitrary name variants, so a journal name copied
from Google Scholar's h5-index page will often silently return zero hits
until resolved this way.

All 26 groups are `active=True` in this build -- 15 hematologic (journals =
AML_JOURNALS) and 11 solid-tumor (journals = ONCOLOGY_JOURNALS). Every MeSH
heading was verified live via `db=mesh` (2026-07-01/02) and every journal
[Journal] term + ISSN resolved live against PubMed. Adding a group is
config-only: fill in `mesh_terms`, `journals`, `ctgov_condition`, verify them
the same way (see the AML `mesh_verified` note), then flip `active=True`.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Journal:
    name: str
    pubmed_filter_term: str  # verified string for the PubMed [Journal] field
    issn_print: str | None
    issn_electronic: str | None
    tier: int  # 1 (core clinical) or 2 (Scholar h5-index top-20)


# --- Tier 1: core clinical (verified 2026-07-01) --------------------------
TIER1_JOURNALS: list[Journal] = [
    Journal("New England Journal of Medicine", "N Engl J Med", "0028-4793", "1533-4406", 1),
    Journal("The Lancet", "Lancet", "0140-6736", "1474-547X", 1),
    Journal("JAMA", "JAMA", "0098-7484", "1538-3598", 1),
    Journal("Nature Medicine", "Nature Medicine", "1078-8956", "1546-170X", 1),
    Journal("Journal of Clinical Oncology", "J Clin Oncol", "0732-183X", "1527-7755", 1),
    Journal("The Lancet Oncology", "The Lancet Oncology", "1470-2045", "1474-5488", 1),
    Journal("JAMA Oncology", "JAMA Oncology", "2374-2437", "2374-2445", 1),
    Journal("Annals of Oncology", "Ann Oncol", "0923-7534", "1569-8041", 1),
    Journal("Blood", "Blood", "0006-4971", "1528-0020", 1),
    Journal("The Lancet Haematology", "The Lancet Haematology", None, "2352-3026", 1),
    Journal("Blood Advances", "Blood Advances", "2473-9529", "2473-9537", 1),
    Journal("Haematologica", "Haematologica", "0390-6078", "1592-8721", 1),
]

# --- Tier 2: Hematology, top ~20 by Google Scholar h5-index ---------------
# (verified 2026-07-01; entries already in TIER1_JOURNALS are not repeated)
TIER2_HEMATOLOGY_JOURNALS: list[Journal] = [
    Journal("Leukemia", "Leukemia", "0887-6924", "1476-5551", 2),
    Journal("Journal of Hematology & Oncology", "Journal of Hematology & Oncology", None, "1756-8722", 2),
    Journal("Journal of Thrombosis and Haemostasis", "J Thromb Haemost", None, "1538-7836", 2),
    Journal("American Journal of Hematology", "American Journal of Hematology", "0361-8609", "1096-8652", 2),
    Journal("Blood Cancer Journal", "Blood Cancer Journal", None, "2044-5385", 2),
    Journal("British Journal of Haematology", "British Journal of Haematology", "0007-1048", "1365-2141", 2),
    Journal("Experimental Hematology & Oncology", "Experimental Hematology & Oncology", "2162-3619", None, 2),
    Journal("Bone Marrow Transplantation", "Bone Marrow Transplantation", "0268-3369", "1476-5365", 2),
    Journal("HemaSphere", "HemaSphere", None, "2572-9241", 2),
    Journal("Blood Reviews", "Blood Reviews", "0268-960X", "1532-1681", 2),
    Journal("Thrombosis and Haemostasis", "Thrombosis and Haemostasis", "0340-6245", "2567-689X", 2),
    Journal("Transplantation and Cellular Therapy", "Transplantation and Cellular Therapy", None, "2666-6367", 2),
    Journal("Leukemia & Lymphoma", "Leukemia & Lymphoma", "1026-8022", "1029-2403", 2),
    Journal("Annals of Hematology", "Annals of Hematology", "0939-5555", "1432-0584", 2),
    Journal("Transfusion", "Transfusion", "0041-1132", "1537-2995", 2),
    Journal("Seminars in Hematology", "Seminars in Hematology", "0037-1963", "1532-8686", 2),
    Journal(
        "Research and Practice in Thrombosis and Haemostasis",
        "Research and Practice in Thrombosis and Haemostasis",
        None, "2475-0379", 2,
    ),
    # Cancers, Frontiers in Oncology, Molecular Cancer, Nature Reviews *:
    # oncology-tier titles, not part of the hematology top-20 -- omitted here.
]

# --- Tier 2: Oncology, top ~20 by Google Scholar h5-index -----------------
# (PubMed [Journal] terms + ISSNs resolved live 2026-07-02; titles already in
# TIER1 (JCO, Lancet Oncol, JAMA Oncol, Ann Oncol) or Tier 2-Heme (J Hematol
# Oncol) are not repeated here.)
# CAVEAT (per the system prompt): several of these -- Cancers, Frontiers in
# Oncology, Molecular Cancer, and the Nature Reviews titles -- are high-volume
# or review-heavy and rarely carry primary phase II/III trial data. They stay
# in the [Journal] filter because the publication-type filter already screens
# out reviews; do not weight them like Tier 1 when reading the digest.
TIER2_ONCOLOGY_JOURNALS: list[Journal] = [
    Journal("CA: A Cancer Journal for Clinicians", "CA Cancer J Clin", "0007-9235", "1542-4863", 2),
    Journal("Cancers", "Cancers (Basel)", None, "2072-6694", 2),
    Journal("Nature Reviews Clinical Oncology", "Nat Rev Clin Oncol", "1759-4774", "1759-4782", 2),
    Journal("Nature Reviews Cancer", "Nat Rev Cancer", "1474-175X", "1474-1768", 2),
    Journal("Clinical Cancer Research", "Clin Cancer Res", "1078-0432", "1557-3265", 2),
    Journal("Cancer Cell", "Cancer Cell", "1535-6108", "1878-3686", 2),
    Journal("Cancer Research", "Cancer Res", "0008-5472", "1538-7445", 2),
    Journal("Molecular Cancer", "Molecular Cancer", None, "1476-4598", 2),
    Journal("Cancer Discovery", "Cancer Discovery", "2159-8274", "2159-8290", 2),
    Journal("Nature Cancer", "Nature Cancer", None, "2662-1347", 2),
    Journal("Journal for ImmunoTherapy of Cancer", "J Immunother Cancer", None, "2051-1426", 2),
    Journal("Journal of Experimental & Clinical Cancer Research", "J Exp Clin Cancer Res", "0392-9078", "1756-9966", 2),
    Journal("Frontiers in Oncology", "Frontiers in Oncology", None, "2234-943X", 2),
    Journal("Cancer Communications", "Cancer Commun (Lond)", None, "2523-3548", 2),
    Journal("Cancer Letters", "Cancer Letters", "0304-3835", "1872-7980", 2),
]

_J_HEM_ONC = [j for j in TIER2_HEMATOLOGY_JOURNALS if j.name == "Journal of Hematology & Oncology"]

AML_JOURNALS: list[Journal] = TIER1_JOURNALS + TIER2_HEMATOLOGY_JOURNALS
# Solid-tumor groups: Tier 1 core + Tier 2 Oncology (+ J Hematol Oncol, which
# the prompt lists in both Scholar top-20s).
ONCOLOGY_JOURNALS: list[Journal] = TIER1_JOURNALS + TIER2_ONCOLOGY_JOURNALS + _J_HEM_ONC

DEFAULT_PUBLICATION_TYPES = [
    "Clinical Trial, Phase III",
    "Clinical Trial, Phase II",
    "Guideline",
    "Practice Guideline",
]


@dataclass(frozen=True)
class GroupOverride:
    also_include_record_types: list[str] = field(default_factory=list)
    window_days: int | None = None  # None = inherit default
    extra_exclusions: list[str] = field(default_factory=list)
    notes: str = ""


PER_GROUP_OVERRIDES: dict[str, GroupOverride] = {
    "chip": GroupOverride(
        also_include_record_types=[
            "Observational Study", "Comparative Study", "Multicenter Study",
        ],
        window_days=30,
        extra_exclusions=["single-patient case reports", "basic-science mechanism papers with no clinical outcome"],
        notes=(
            "CHIP literature is largely observational, not phase II/III. "
            "also_include_record_types are UNIONED (OR) with "
            "DEFAULT_PUBLICATION_TYPES, per the paired system prompt's "
            "'ALSO include' framing -- guidelines/trials are still eligible, "
            "this just widens the net rather than narrowing it."
        ),
    ),
    "sickle_cell": GroupOverride(
        also_include_record_types=["Clinical Trial", "Observational Study"],
        notes="Also include pivotal single-arm and gene/cell-therapy studies; keep phase II/III as usual.",
    ),
}


@dataclass(frozen=True)
class DiseaseGroup:
    key: str
    label: str
    category: str  # "hematologic" | "solid_tumor"
    mesh_terms: list[str]
    journals: list[Journal]
    # Vestigial: ClinicalTrials.gov retrieval was removed (the pipeline now
    # surfaces published PubMed papers only). Retained as documentation of the
    # condition string, in case registry retrieval is re-added later.
    ctgov_condition: str
    window_days: int = 14
    active: bool = False
    mesh_verified: bool = False


DISEASE_GROUPS: dict[str, DiseaseGroup] = {
    "aml": DiseaseGroup(
        key="aml",
        label="Acute Myeloid Leukemia",
        category="hematologic",
        mesh_terms=["Leukemia, Myeloid, Acute"],
        journals=AML_JOURNALS,
        ctgov_condition="acute myeloid leukemia",
        window_days=14,
        active=True,
        mesh_verified=True,  # confirmed via db=mesh esearch, 2026-07-01
    ),
    # --- Hematologic groups: all MeSH headings below were verified live
    # against NCBI (db=mesh esearch, 2026-07-02) and journals share the same
    # verified AML_JOURNALS set (Tier 1 + Tier 2-Hematology), so these are
    # active. CHIP and sickle cell carry PER_GROUP_OVERRIDES (see above).
    "mds": DiseaseGroup("mds", "Myelodysplastic Syndromes", "hematologic",
                         ["Myelodysplastic Syndromes"], AML_JOURNALS, "myelodysplastic syndrome",
                         active=True, mesh_verified=True),
    "mpn": DiseaseGroup("mpn", "Myeloproliferative Neoplasms", "hematologic",
                         ["Myeloproliferative Disorders"], AML_JOURNALS, "myeloproliferative neoplasm",
                         active=True, mesh_verified=True),
    "cll": DiseaseGroup("cll", "Chronic Lymphocytic Leukemia", "hematologic",
                         ["Leukemia, Lymphocytic, Chronic, B-Cell"], AML_JOURNALS, "chronic lymphocytic leukemia",
                         active=True, mesh_verified=True),
    "dlbcl": DiseaseGroup("dlbcl", "Diffuse Large B-Cell Lymphoma", "hematologic",
                           ["Lymphoma, Large B-Cell, Diffuse"], AML_JOURNALS, "diffuse large B-cell lymphoma",
                           active=True, mesh_verified=True),
    "follicular_lymphoma": DiseaseGroup("follicular_lymphoma", "Follicular Lymphoma", "hematologic",
                                         ["Lymphoma, Follicular"], AML_JOURNALS, "follicular lymphoma",
                                         active=True, mesh_verified=True),
    "mantle_cell_lymphoma": DiseaseGroup("mantle_cell_lymphoma", "Mantle Cell Lymphoma", "hematologic",
                                          ["Lymphoma, Mantle-Cell"], AML_JOURNALS, "mantle cell lymphoma",
                                          active=True, mesh_verified=True),
    "marginal_zone_lymphoma": DiseaseGroup("marginal_zone_lymphoma", "Marginal Zone Lymphoma", "hematologic",
                                            ["Lymphoma, B-Cell, Marginal Zone"], AML_JOURNALS, "marginal zone lymphoma",
                                            active=True, mesh_verified=True),
    "hodgkin": DiseaseGroup("hodgkin", "Hodgkin Lymphoma", "hematologic",
                             ["Hodgkin Disease"], AML_JOURNALS, "Hodgkin lymphoma",
                             active=True, mesh_verified=True),
    "multiple_myeloma": DiseaseGroup("multiple_myeloma", "Multiple Myeloma", "hematologic",
                                      ["Multiple Myeloma"], AML_JOURNALS, "multiple myeloma",
                                      active=True, mesh_verified=True),
    "all": DiseaseGroup("all", "Acute Lymphoblastic Leukemia", "hematologic",
                         ["Precursor Cell Lymphoblastic Leukemia-Lymphoma"], AML_JOURNALS,
                         "acute lymphoblastic leukemia", active=True, mesh_verified=True),
    "cml": DiseaseGroup("cml", "Chronic Myeloid Leukemia", "hematologic",
                         ["Leukemia, Myelogenous, Chronic, BCR-ABL Positive"], AML_JOURNALS,
                         "chronic myeloid leukemia", active=True, mesh_verified=True),
    "aplastic_anemia": DiseaseGroup("aplastic_anemia", "Aplastic Anemia", "hematologic",
                                     ["Anemia, Aplastic"], AML_JOURNALS, "aplastic anemia",
                                     active=True, mesh_verified=True),
    "chip": DiseaseGroup("chip", "Clonal Hematopoiesis of Indeterminate Potential", "hematologic",
                          ["Clonal Hematopoiesis"], AML_JOURNALS, "clonal hematopoiesis", window_days=30,
                          active=True, mesh_verified=True),
    "sickle_cell": DiseaseGroup("sickle_cell", "Sickle Cell Disease", "hematologic",
                                 ["Anemia, Sickle Cell"], AML_JOURNALS, "sickle cell disease",
                                 active=True, mesh_verified=True),
    # --- Solid-tumor groups: MeSH headings verified live via db=mesh esearch
    # (2026-07-02); journals use ONCOLOGY_JOURNALS (Tier 1 + Tier 2 Oncology,
    # resolved live the same day). Active.
    "head_neck": DiseaseGroup("head_neck", "Head and Neck Cancer", "solid_tumor",
                               ["Head and Neck Neoplasms", "Squamous Cell Carcinoma of Head and Neck"],
                               ONCOLOGY_JOURNALS, "head and neck cancer",
                               active=True, mesh_verified=True),
    "breast": DiseaseGroup("breast", "Breast Cancer", "solid_tumor",
                            ["Breast Neoplasms"], ONCOLOGY_JOURNALS, "breast cancer",
                            active=True, mesh_verified=True),
    "lung": DiseaseGroup("lung", "Lung Cancer", "solid_tumor",
                          ["Lung Neoplasms", "Carcinoma, Non-Small-Cell Lung", "Small Cell Lung Carcinoma"],
                          ONCOLOGY_JOURNALS, "lung cancer", active=True, mesh_verified=True),
    "pancreatic": DiseaseGroup("pancreatic", "Pancreatic Cancer", "solid_tumor",
                                ["Pancreatic Neoplasms", "Carcinoma, Pancreatic Ductal"],
                                ONCOLOGY_JOURNALS, "pancreatic cancer", active=True, mesh_verified=True),
    "gastric": DiseaseGroup("gastric", "Gastric Cancer", "solid_tumor",
                             ["Stomach Neoplasms"], ONCOLOGY_JOURNALS, "gastric cancer",
                             active=True, mesh_verified=True),
    "liver": DiseaseGroup("liver", "Hepatocellular/Biliary Cancer", "solid_tumor",
                           ["Carcinoma, Hepatocellular", "Liver Neoplasms", "Cholangiocarcinoma", "Bile Duct Neoplasms"],
                           ONCOLOGY_JOURNALS, "hepatocellular carcinoma", active=True, mesh_verified=True),
    "colorectal": DiseaseGroup("colorectal", "Colorectal Cancer", "solid_tumor",
                                ["Colorectal Neoplasms"], ONCOLOGY_JOURNALS, "colorectal cancer",
                                active=True, mesh_verified=True),
    "melanoma": DiseaseGroup("melanoma", "Melanoma", "solid_tumor",
                              ["Melanoma"], ONCOLOGY_JOURNALS, "melanoma",
                              active=True, mesh_verified=True),
    "prostate": DiseaseGroup("prostate", "Prostate Cancer", "solid_tumor",
                              ["Prostatic Neoplasms"], ONCOLOGY_JOURNALS, "prostate cancer",
                              active=True, mesh_verified=True),
    "sarcomas": DiseaseGroup("sarcomas", "Sarcomas", "solid_tumor",
                              ["Sarcoma"], ONCOLOGY_JOURNALS, "sarcoma",
                              active=True, mesh_verified=True),
    "thyroid": DiseaseGroup("thyroid", "Thyroid Cancer", "solid_tumor",
                             ["Thyroid Neoplasms"], ONCOLOGY_JOURNALS, "thyroid cancer",
                             active=True, mesh_verified=True),
}

ACTIVE_GROUPS = [g for g in DISEASE_GROUPS.values() if g.active]

SYSTEM_PROMPT_PATH = "heme_onc_literature_surveillance_prompt.md"
DB_PATH = "data/surveillance.db"
DIGESTS_DIR = "digests"

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_MAX_TOKENS = 6000

NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
