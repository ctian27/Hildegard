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

Only AML (`disease_groups["aml"]`) is `active=True` in this build. Adding a
new group is meant to be config-only: fill in `mesh_terms`, `journals`,
`ctgov_condition`, verify them the same way AML was verified, then flip
`active=True`.
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

# NOT yet resolved/verified -- placeholder names only, needed before any
# solid-tumor group is activated. Do not wire into a PubMed [Journal] filter
# until each is verified the same way as TIER1/TIER2_HEMATOLOGY above.
TIER2_ONCOLOGY_JOURNALS_UNVERIFIED: list[str] = [
    "CA: A Cancer Journal for Clinicians", "Cancers", "Nature Reviews Clinical Oncology",
    "Nature Reviews Cancer", "Clinical Cancer Research", "Cancer Cell", "Cancer Research",
    "Molecular Cancer", "Cancer Discovery", "Nature Cancer",
    "Journal for ImmunoTherapy of Cancer", "Journal of Experimental & Clinical Cancer Research",
    "Frontiers in Oncology", "Cancer Communications", "Cancer Letters",
]

AML_JOURNALS: list[Journal] = TIER1_JOURNALS + TIER2_HEMATOLOGY_JOURNALS

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
    # --- Remaining groups: MeSH terms below are carried over from the build
    # brief's mapping table and are NOT independently verified yet. Journals
    # default to the same-category union but are also unverified for
    # journals outside TIER1/TIER2_HEMATOLOGY. Verify (see AML's mesh_verified
    # comment above) and set active=True before including in a live cycle.
    "mds": DiseaseGroup("mds", "Myelodysplastic Syndromes", "hematologic",
                         ["Myelodysplastic Syndromes"], AML_JOURNALS, "myelodysplastic syndrome"),
    "mpn": DiseaseGroup("mpn", "Myeloproliferative Neoplasms", "hematologic",
                         ["Myeloproliferative Disorders"], AML_JOURNALS, "myeloproliferative neoplasm"),
    "cll": DiseaseGroup("cll", "Chronic Lymphocytic Leukemia", "hematologic",
                         ["Leukemia, Lymphocytic, Chronic, B-Cell"], AML_JOURNALS, "chronic lymphocytic leukemia"),
    "dlbcl": DiseaseGroup("dlbcl", "Diffuse Large B-Cell Lymphoma", "hematologic",
                           ["Lymphoma, Large B-Cell, Diffuse"], AML_JOURNALS, "diffuse large B-cell lymphoma"),
    "follicular_lymphoma": DiseaseGroup("follicular_lymphoma", "Follicular Lymphoma", "hematologic",
                                         ["Lymphoma, Follicular"], AML_JOURNALS, "follicular lymphoma"),
    "mantle_cell_lymphoma": DiseaseGroup("mantle_cell_lymphoma", "Mantle Cell Lymphoma", "hematologic",
                                          ["Lymphoma, Mantle-Cell"], AML_JOURNALS, "mantle cell lymphoma"),
    "marginal_zone_lymphoma": DiseaseGroup("marginal_zone_lymphoma", "Marginal Zone Lymphoma", "hematologic",
                                            ["Lymphoma, B-Cell, Marginal Zone"], AML_JOURNALS, "marginal zone lymphoma"),
    "hodgkin": DiseaseGroup("hodgkin", "Hodgkin Lymphoma", "hematologic",
                             ["Hodgkin Disease"], AML_JOURNALS, "Hodgkin lymphoma"),
    "multiple_myeloma": DiseaseGroup("multiple_myeloma", "Multiple Myeloma", "hematologic",
                                      ["Multiple Myeloma"], AML_JOURNALS, "multiple myeloma"),
    "all": DiseaseGroup("all", "Acute Lymphoblastic Leukemia", "hematologic",
                         ["Precursor Cell Lymphoblastic Leukemia-Lymphoma"], AML_JOURNALS,
                         "acute lymphoblastic leukemia"),
    "cml": DiseaseGroup("cml", "Chronic Myeloid Leukemia", "hematologic",
                         ["Leukemia, Myelogenous, Chronic, BCR-ABL Positive"], AML_JOURNALS,
                         "chronic myeloid leukemia"),
    "aplastic_anemia": DiseaseGroup("aplastic_anemia", "Aplastic Anemia", "hematologic",
                                     ["Anemia, Aplastic"], AML_JOURNALS, "aplastic anemia"),
    "chip": DiseaseGroup("chip", "Clonal Hematopoiesis of Indeterminate Potential", "hematologic",
                          ["Clonal Hematopoiesis"], AML_JOURNALS, "clonal hematopoiesis", window_days=30),
    "sickle_cell": DiseaseGroup("sickle_cell", "Sickle Cell Disease", "hematologic",
                                 ["Anemia, Sickle Cell"], AML_JOURNALS, "sickle cell disease"),
    "head_neck": DiseaseGroup("head_neck", "Head and Neck Cancer", "solid_tumor",
                               ["Head and Neck Neoplasms", "Squamous Cell Carcinoma of Head and Neck"],
                               TIER1_JOURNALS, "head and neck cancer"),
    "breast": DiseaseGroup("breast", "Breast Cancer", "solid_tumor",
                            ["Breast Neoplasms"], TIER1_JOURNALS, "breast cancer"),
    "lung": DiseaseGroup("lung", "Lung Cancer", "solid_tumor",
                          ["Lung Neoplasms", "Carcinoma, Non-Small-Cell Lung", "Small Cell Lung Carcinoma"],
                          TIER1_JOURNALS, "lung cancer"),
    "pancreatic": DiseaseGroup("pancreatic", "Pancreatic Cancer", "solid_tumor",
                                ["Pancreatic Neoplasms", "Carcinoma, Pancreatic Ductal"],
                                TIER1_JOURNALS, "pancreatic cancer"),
    "gastric": DiseaseGroup("gastric", "Gastric Cancer", "solid_tumor",
                             ["Stomach Neoplasms"], TIER1_JOURNALS, "gastric cancer"),
    "liver": DiseaseGroup("liver", "Hepatocellular/Biliary Cancer", "solid_tumor",
                           ["Carcinoma, Hepatocellular", "Liver Neoplasms", "Cholangiocarcinoma", "Bile Duct Neoplasms"],
                           TIER1_JOURNALS, "hepatocellular carcinoma"),
    "colorectal": DiseaseGroup("colorectal", "Colorectal Cancer", "solid_tumor",
                                ["Colorectal Neoplasms"], TIER1_JOURNALS, "colorectal cancer"),
    "melanoma": DiseaseGroup("melanoma", "Melanoma", "solid_tumor",
                              ["Melanoma"], TIER1_JOURNALS, "melanoma"),
    "prostate": DiseaseGroup("prostate", "Prostate Cancer", "solid_tumor",
                              ["Prostatic Neoplasms"], TIER1_JOURNALS, "prostate cancer"),
    "sarcomas": DiseaseGroup("sarcomas", "Sarcomas", "solid_tumor",
                              ["Sarcoma"], TIER1_JOURNALS, "sarcoma"),
    "thyroid": DiseaseGroup("thyroid", "Thyroid Cancer", "solid_tumor",
                             ["Thyroid Neoplasms"], TIER1_JOURNALS, "thyroid cancer"),
}

ACTIVE_GROUPS = [g for g in DISEASE_GROUPS.values() if g.active]

SYSTEM_PROMPT_PATH = "heme_onc_literature_surveillance_prompt.md"
DB_PATH = "data/surveillance.db"
DIGESTS_DIR = "digests"

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_MAX_TOKENS = 6000

NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"
