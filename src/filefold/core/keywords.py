from enum import Enum


class Category(str, Enum):
    MESH = "mesh"
    SECTION = "section"
    MATERIAL = "material"
    STEP = "step"
    LOADS = "loads"
    CONTACT = "contact"
    OUTPUT = "output"
    MODEL = "model"
    UNKNOWN = "unknown"


# Normalized keyword (uppercase, no leading asterisk) -> Category
KEYWORD_CATEGORIES: dict[str, Category] = {
    # MESH — geometry and topology (including part containers from CAE-format files)
    "NODE": Category.MESH,
    "ELEMENT": Category.MESH,
    "NSET": Category.MESH,
    "ELSET": Category.MESH,
    "SURFACE": Category.MESH,
    "PART": Category.MESH,
    "END PART": Category.MESH,

    # SECTION — property assignment linking elements to materials
    "SOLID SECTION": Category.SECTION,
    "SHELL SECTION": Category.SECTION,
    "SHELL GENERAL SECTION": Category.SECTION,
    "BEAM SECTION": Category.SECTION,
    "MEMBRANE SECTION": Category.SECTION,
    "COHESIVE SECTION": Category.SECTION,
    "GASKET SECTION": Category.SECTION,

    # MATERIAL — material property definitions
    "MATERIAL": Category.MATERIAL,
    "ELASTIC": Category.MATERIAL,
    "PLASTIC": Category.MATERIAL,
    "DENSITY": Category.MATERIAL,
    "EXPANSION": Category.MATERIAL,
    "CONDUCTIVITY": Category.MATERIAL,
    "SPECIFIC HEAT": Category.MATERIAL,
    "DAMPING": Category.MATERIAL,
    "HYPERELASTIC": Category.MATERIAL,
    "VISCOELASTIC": Category.MATERIAL,
    "CREEP": Category.MATERIAL,
    "RATE DEPENDENT": Category.MATERIAL,

    # STEP — analysis step containers and procedure keywords
    "STEP": Category.STEP,
    "END STEP": Category.STEP,
    "STATIC": Category.STEP,
    "DYNAMIC": Category.STEP,
    "DYNAMIC EXPLICIT": Category.STEP,
    "VISCO": Category.STEP,
    "FREQUENCY": Category.STEP,
    "BUCKLE": Category.STEP,
    "HEAT TRANSFER": Category.STEP,
    "COUPLED TEMP-DISPLACEMENT": Category.STEP,
    "MASS DIFFUSION": Category.STEP,

    # LOADS — applied loads, boundary conditions, and their time curves
    "BOUNDARY": Category.LOADS,
    "CLOAD": Category.LOADS,
    "DLOAD": Category.LOADS,
    "DSLOAD": Category.LOADS,
    "DFLUX": Category.LOADS,
    "CFLUX": Category.LOADS,
    "TEMPERATURE": Category.LOADS,
    "AMPLITUDE": Category.LOADS,

    # CONTACT — contact pair definitions, interactions, and interference
    "CONTACT PAIR": Category.CONTACT,
    "SURFACE INTERACTION": Category.CONTACT,
    "FRICTION": Category.CONTACT,
    "CONTACT INTERFERENCE": Category.CONTACT,
    "MODEL CHANGE": Category.CONTACT,
    "CONTACT PROPERTY ASSIGNMENT": Category.CONTACT,

    # OUTPUT — all output requests (ODB fields, history, print, restart)
    "OUTPUT": Category.OUTPUT,
    "NODE OUTPUT": Category.OUTPUT,
    "ELEMENT OUTPUT": Category.OUTPUT,
    "CONTACT OUTPUT": Category.OUTPUT,
    "NODE FILE": Category.OUTPUT,
    "EL FILE": Category.OUTPUT,
    "CONTACT FILE": Category.OUTPUT,
    "NODE PRINT": Category.OUTPUT,
    "EL PRINT": Category.OUTPUT,
    "CONTACT PRINT": Category.OUTPUT,
    "ENERGY PRINT": Category.OUTPUT,
    "TORQUE PRINT": Category.OUTPUT,
    "PRINT": Category.OUTPUT,
    "RESTART": Category.OUTPUT,

    # MODEL — model-level metadata, control directives, and assembly structure
    "HEADING": Category.MODEL,
    "PREPRINT": Category.MODEL,
    "INCLUDE": Category.MODEL,
    "ASSEMBLY": Category.MODEL,
    "END ASSEMBLY": Category.MODEL,
    "INSTANCE": Category.MODEL,
    "END INSTANCE": Category.MODEL,
}


def categorize(keyword: str) -> Category:
    """Return the Category for a keyword string (leading * and params stripped, any case)."""
    return KEYWORD_CATEGORIES.get(keyword.strip().upper(), Category.UNKNOWN)


# ---------------------------------------------------------------------------
# Sub-category definitions
# ---------------------------------------------------------------------------

# Maps keyword (normalized) -> sub_category name within MESH
MESH_SUB_KEYWORDS: dict[str, str] = {
    "NODE":    "nodes",
    "NGEN":    "nodes",
    "NCOPY":   "nodes",
    "ELEMENT": "elements",
    "ELGEN":   "elements",
    "ELCOPY":  "elements",
    "NSET":    "nsets",
    "ELSET":   "elsets",
    "SURFACE": "surfaces",
}

# Maps Category -> {keyword -> sub_category name}
CATEGORY_SUB_KEYWORDS: dict[Category, dict[str, str]] = {
    Category.MESH: MESH_SUB_KEYWORDS,
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
}
