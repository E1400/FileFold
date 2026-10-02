from enum import Enum


class Category(str, Enum):
    MESH = "mesh"
    SECTION = "section"
    MATERIAL = "material"
    STEP = "step"
    LOADS = "loads"
    CONTACT = "contact"
    CONSTRAINT = "constraint"
    INITIAL = "initial"
    OUTPUT = "output"
    MODEL = "model"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Keyword registry
#
# Grouped by category for readability; flattened into KEYWORD_CATEGORIES below.
# Keywords are normalized: uppercase, no leading asterisk, single spaces.
#
# STATUS: compiled from working knowledge of the Abaqus Keywords Reference, not
# yet cross-checked line by line against the official docs. Anything missing is
# not a correctness risk: the parser attaches an unmapped keyword to the block
# before it (see parser.py), so an option can never be separated from its parent.
# ---------------------------------------------------------------------------

_REGISTRY: dict[Category, tuple[str, ...]] = {
    # Geometry and topology (including part containers from CAE-format files)
    Category.MESH: (
        "NODE", "NGEN", "NCOPY", "NFILL", "NMAP", "NSET",
        "ELEMENT", "ELGEN", "ELCOPY", "ELSET",
        "SURFACE", "SYSTEM", "TRANSFORM",
        "PART", "END PART",
    ),

    # Property assignment linking elements to materials / physical properties
    Category.SECTION: (
        "SOLID SECTION", "SHELL SECTION", "SHELL GENERAL SECTION", "BEAM SECTION",
        "BEAM GENERAL SECTION", "MEMBRANE SECTION", "COHESIVE SECTION", "GASKET SECTION",
        "SURFACE SECTION", "EULERIAN SECTION", "FRAME SECTION", "SECTION CONTROLS",
        "TRANSVERSE SHEAR STIFFNESS", "REBAR LAYER", "REBAR", "ORIENTATION",
        "DISTRIBUTION", "DISTRIBUTION TABLE", "HOURGLASS STIFFNESS",
        "MASS", "ROTARY INERTIA", "NONSTRUCTURAL MASS", "SPRING", "DASHPOT",
        "CONNECTOR SECTION", "CONNECTOR BEHAVIOR",
    ),

    # Material property definitions and their options
    Category.MATERIAL: (
        "MATERIAL", "ELASTIC", "PLASTIC", "DENSITY", "EXPANSION", "CONDUCTIVITY",
        "SPECIFIC HEAT", "DAMPING", "HYPERELASTIC", "HYPERFOAM", "VISCOELASTIC",
        "CREEP", "RATE DEPENDENT", "DEPVAR", "USER MATERIAL", "MULLINS EFFECT",
        "VISCOSITY", "EOS", "LATENT HEAT", "INELASTIC HEAT FRACTION", "SWELLING",
        "TENSION CUTOFF", "FAILURE RATIOS", "SHEAR FAILURE", "TENSILE FAILURE",
        "PERMEABILITY", "SORPTION", "POROUS ELASTIC", "CLAY PLASTICITY",
        "CAP PLASTICITY", "CAP HARDENING", "CAP CREEP", "CYCLIC HARDENING",
        "ELECTRICAL CONDUCTIVITY", "PIEZOELECTRIC", "DIELECTRIC", "TRS", "HYSTERESIS",
        "UNIAXIAL TEST DATA", "BIAXIAL TEST DATA", "PLANAR TEST DATA",
        "VOLUMETRIC TEST DATA", "SHEAR TEST DATA", "FLUID BEHAVIOR",
    ),

    # Constraints between degrees of freedom
    Category.CONSTRAINT: (
        "TIE", "COUPLING", "KINEMATIC", "DISTRIBUTING", "KINEMATIC COUPLING",
        "DISTRIBUTING COUPLING", "SHELL TO SOLID COUPLING", "MPC", "EQUATION",
        "RIGID BODY", "EMBEDDED ELEMENT", "CONSTRAINT CONTROLS", "FASTENER",
    ),

    # Initial state of the model
    Category.INITIAL: (
        "INITIAL CONDITIONS", "FIELD",
    ),

    # Analysis step containers and procedure keywords
    Category.STEP: (
        "STEP", "END STEP", "STATIC", "DYNAMIC", "DYNAMIC EXPLICIT", "VISCO",
        "FREQUENCY", "BUCKLE", "HEAT TRANSFER", "COUPLED TEMP-DISPLACEMENT",
        "MASS DIFFUSION", "MODAL DYNAMIC", "STEADY STATE DYNAMICS", "RANDOM RESPONSE",
        "RESPONSE SPECTRUM", "COMPLEX FREQUENCY", "DIRECT CYCLIC", "GEOSTATIC", "SOILS",
        "ANNEAL", "SUBSTRUCTURE GENERATE", "SELECT EIGENMODES", "CONTROLS",
        "SOLVER CONTROLS", "INERTIA RELIEF", "STEP CONTROLS",
    ),

    # Applied loads, boundary conditions, and their time curves
    Category.LOADS: (
        "BOUNDARY", "CLOAD", "DLOAD", "DSLOAD", "DFLUX", "CFLUX", "TEMPERATURE",
        "AMPLITUDE", "FILM", "SFILM", "CFILM", "RADIATE", "SRADIATE", "CRADIATE",
        "PRESSURE PENETRATION", "IMPERFECTION", "BUOYANCY",
    ),

    # Contact pairs, general contact, interactions, and interference
    Category.CONTACT: (
        "CONTACT PAIR", "CONTACT", "SURFACE INTERACTION", "SURFACE BEHAVIOR",
        "FRICTION", "COHESIVE BEHAVIOR", "GAP CONDUCTANCE", "GAP RADIATION",
        "GAP HEAT GENERATION", "CONTACT INTERFERENCE", "CLEARANCE", "SURFACE SMOOTHING",
        "CHANGE FRICTION", "MODEL CHANGE", "CONTACT PROPERTY ASSIGNMENT",
        "CONTACT INCLUSIONS", "CONTACT EXCLUSIONS", "CONTACT CONTROLS",
        "CONTACT CONTROLS ASSIGNMENT", "CONTACT FORMULATION", "CONTACT STABILIZATION",
        "CONTACT CLEARANCE ASSIGNMENT", "CONTACT INITIALIZATION ASSIGNMENT",
        "CONTACT DAMPING",
    ),

    # Output requests (ODB fields, history, print, restart)
    Category.OUTPUT: (
        "OUTPUT", "NODE OUTPUT", "ELEMENT OUTPUT", "CONTACT OUTPUT", "ENERGY OUTPUT",
        "INTEGRATED OUTPUT", "INTEGRATED OUTPUT SECTION", "SURFACE OUTPUT",
        "MODAL OUTPUT", "NODE FILE", "EL FILE", "CONTACT FILE", "ENERGY FILE",
        "SECTION FILE", "NODE PRINT", "EL PRINT", "CONTACT PRINT", "ENERGY PRINT",
        "TORQUE PRINT", "SECTION PRINT", "PRINT", "RESTART", "FILE FORMAT",
        "MONITOR", "TIME POINTS", "DIAGNOSTICS", "USER OUTPUT VARIABLES",
    ),

    # Model-level metadata, control directives, and assembly structure
    Category.MODEL: (
        "HEADING", "PREPRINT", "INCLUDE", "PARAMETER", "PHYSICAL CONSTANTS",
        "ASSEMBLY", "END ASSEMBLY", "INSTANCE", "END INSTANCE",
    ),
}

# Families of keywords that share a prefix (checked only after the explicit table).
_PREFIX_RULES: tuple[tuple[str, Category], ...] = (
    ("HYPER", Category.MATERIAL),
    ("DAMAGE ", Category.MATERIAL),
    ("CONCRETE", Category.MATERIAL),
    ("DRUCKER PRAGER", Category.MATERIAL),
    ("MOHR COULOMB", Category.MATERIAL),
    ("GASKET ", Category.MATERIAL),
    ("BRITTLE ", Category.MATERIAL),
    ("CAP ", Category.MATERIAL),
    ("POROUS ", Category.MATERIAL),
    ("CYCLIC ", Category.MATERIAL),
    ("CONNECTOR ", Category.SECTION),
    ("CONTACT ", Category.CONTACT),
)

# Normalized keyword (uppercase, no leading asterisk) -> Category
KEYWORD_CATEGORIES: dict[str, Category] = {
    kw: cat for cat, kws in _REGISTRY.items() for kw in kws
}


def normalize(keyword: str) -> str:
    """Uppercase, strip a leading *, collapse internal whitespace."""
    return " ".join(keyword.lstrip().lstrip("*").upper().split())


def categorize(keyword: str) -> Category:
    """Return the Category for a keyword string (leading * and params stripped, any case).

    UNKNOWN means the registry has no opinion; the parser then inherits the category
    of the preceding block (see parser.parse) rather than leaving it unknown.
    """
    kw = normalize(keyword)
    cat = KEYWORD_CATEGORIES.get(kw)
    if cat is not None:
        return cat
    for prefix, pcat in _PREFIX_RULES:
        if kw.startswith(prefix):
            return pcat
    return Category.UNKNOWN


# ---------------------------------------------------------------------------
# Sub-category definitions
# ---------------------------------------------------------------------------

# Maps keyword (normalized) -> sub_category name within MESH
MESH_SUB_KEYWORDS: dict[str, str] = {
    "NODE":    "nodes",
    "NGEN":    "nodes",
    "NCOPY":   "nodes",
    "NFILL":   "nodes",
    "NMAP":    "nodes",
    "ELEMENT": "elements",
    "ELGEN":   "elements",
    "ELCOPY":  "elements",
    "NSET":    "nsets",
    "ELSET":   "elsets",
    "SURFACE": "surfaces",
}

# CONTACT — every registered contact keyword is mapped so that an interaction's
# options (*FRICTION, *SURFACE BEHAVIOR, ...) always travel with *SURFACE INTERACTION.
CONTACT_SUB_KEYWORDS: dict[str, str] = {
    "CONTACT PAIR": "pairs",
    "CONTACT INTERFERENCE": "pairs",
    "CLEARANCE": "pairs",
    "SURFACE INTERACTION": "interactions",
    "SURFACE BEHAVIOR": "interactions",
    "FRICTION": "interactions",
    "COHESIVE BEHAVIOR": "interactions",
    "GAP CONDUCTANCE": "interactions",
    "GAP RADIATION": "interactions",
    "GAP HEAT GENERATION": "interactions",
    "SURFACE SMOOTHING": "interactions",
    "CONTACT DAMPING": "interactions",
    "CONTACT": "general",
    "CONTACT INCLUSIONS": "general",
    "CONTACT EXCLUSIONS": "general",
    "CONTACT PROPERTY ASSIGNMENT": "general",
    "CONTACT CONTROLS": "general",
    "CONTACT CONTROLS ASSIGNMENT": "general",
    "CONTACT FORMULATION": "general",
    "CONTACT STABILIZATION": "general",
    "CONTACT CLEARANCE ASSIGNMENT": "general",
    "CONTACT INITIALIZATION ASSIGNMENT": "general",
}

CONSTRAINT_SUB_KEYWORDS: dict[str, str] = {
    "TIE": "ties",
    "COUPLING": "couplings",
    "KINEMATIC": "couplings",
    "DISTRIBUTING": "couplings",
    "KINEMATIC COUPLING": "couplings",
    "DISTRIBUTING COUPLING": "couplings",
    "SHELL TO SOLID COUPLING": "couplings",
    "RIGID BODY": "rigid",
    "MPC": "equations",
    "EQUATION": "equations",
}

LOADS_SUB_KEYWORDS: dict[str, str] = {
    "BOUNDARY": "boundary",
    "AMPLITUDE": "amplitudes",
    "CLOAD": "applied",
    "DLOAD": "applied",
    "DSLOAD": "applied",
    "TEMPERATURE": "thermal",
    "DFLUX": "thermal",
    "CFLUX": "thermal",
    "FILM": "thermal",
    "SFILM": "thermal",
    "CFILM": "thermal",
    "RADIATE": "thermal",
    "SRADIATE": "thermal",
    "CRADIATE": "thermal",
}

# Maps Category -> {keyword -> sub_category name}
CATEGORY_SUB_KEYWORDS: dict[Category, dict[str, str]] = {
    Category.MESH: MESH_SUB_KEYWORDS,
    Category.CONTACT: CONTACT_SUB_KEYWORDS,
    Category.CONSTRAINT: CONSTRAINT_SUB_KEYWORDS,
    Category.LOADS: LOADS_SUB_KEYWORDS,
}

# Available sub-categories per category (ordered for UI display)
CATEGORY_SUB_OPTIONS: dict[Category, list[dict[str, str]]] = {
    Category.MESH: [
        {"sub_category": "nodes",    "label": "Nodes (*NODE)",         "default_filename": "mesh-nodes.inp"},
        {"sub_category": "elements", "label": "Elements (*ELEMENT)",   "default_filename": "mesh-elements.inp"},
        {"sub_category": "nsets",    "label": "Node Sets (*NSET)",     "default_filename": "mesh-nsets.inp"},
        {"sub_category": "elsets",   "label": "Element Sets (*ELSET)", "default_filename": "mesh-elsets.inp"},
        {"sub_category": "surfaces", "label": "Surfaces (*SURFACE)",   "default_filename": "mesh-surfaces.inp"},
    ],
    Category.CONTACT: [
        {"sub_category": "pairs",        "label": "Contact Pairs (*CONTACT PAIR)",          "default_filename": "contact-pairs.inp"},
        {"sub_category": "interactions", "label": "Interaction Properties (*SURFACE INTERACTION)", "default_filename": "contact-interactions.inp"},
        {"sub_category": "general",      "label": "General Contact (*CONTACT)",             "default_filename": "contact-general.inp"},
    ],
    Category.CONSTRAINT: [
        {"sub_category": "ties",      "label": "Ties (*TIE)",                      "default_filename": "constraints-ties.inp"},
        {"sub_category": "couplings", "label": "Couplings (*COUPLING)",            "default_filename": "constraints-couplings.inp"},
        {"sub_category": "rigid",     "label": "Rigid Bodies (*RIGID BODY)",       "default_filename": "constraints-rigid.inp"},
        {"sub_category": "equations", "label": "MPCs and Equations (*MPC, *EQUATION)", "default_filename": "constraints-equations.inp"},
    ],
    Category.LOADS: [
        {"sub_category": "boundary",   "label": "Boundary Conditions (*BOUNDARY)",  "default_filename": "loads-boundary.inp"},
        {"sub_category": "amplitudes", "label": "Amplitudes (*AMPLITUDE)",          "default_filename": "loads-amplitudes.inp"},
        {"sub_category": "applied",    "label": "Applied Loads (*CLOAD, *DLOAD)",   "default_filename": "loads-applied.inp"},
        {"sub_category": "thermal",    "label": "Thermal (*TEMPERATURE, *DFLUX)",   "default_filename": "loads-thermal.inp"},
    ],
}
