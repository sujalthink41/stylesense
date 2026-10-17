"""What the stylist will talk about: fashion, politely, and nothing else. Rules only (free).

- unsafe: abuse, slurs, sexual or violent requests. A polite redirect; the text isn't kept.
- off_topic: nothing about clothes, shoes, accessories or what to wear. A friendly redirect.
- question: a fashion question ("what goes with black jeans?"): a short answer + products.
- shop: everything else that's about fashion: search as usual.
"""

import re
from typing import Literal

from stylesense.modules.stylist.brands import find_brand
from stylesense.modules.stylist.understanding import guess_category, parse_request, unknown_words

Verdict = Literal["shop", "question", "off_topic", "unsafe"]

UNSAFE_REPLY = "Let's keep it about style. Ask me what to wear, or search for clothes and shoes."
OFF_TOPIC_REPLY = (
    "I'm your fashion stylist: ask me what to wear, what goes with what, "
    "or search for clothes, shoes and accessories."
)

# Abuse (English and common Hinglish), explicit sexual requests, violence, drugs, self-harm.
# Swimwear, lingerie and colour names (nude, gunmetal) are fashion and stay allowed; words are
# matched whole, so a brand like "Bombay Denim" never trips the filter.
_UNSAFE = re.compile(
    r"\b(?:"
    r"f+u+c+k+\w*|sh[i1]t+\w*|b[i1]tch\w*|bastard\w*|c+u+n+t+\w*|d[i1]ck(?:head)?"
    r"|motherf\w+|wh[o0]re\w*|slut\w*"
    r"|nigg\w+|fag+(?:got)?s?|retard\w*|chut(?:iya|iye|ya)\w*|bhen?chod\w*|madar ?chod\w*"
    r"|bsdk|bc|mc"
    r"|gaand\w*|lund\w*|randi\w*|harami\w*|kamina\w*|saal[ae]? kutt\w*"
    r"|porn\w*|nudes|nude (?:photo|pic|image|video)s?|naked|nsfw|sexting|sex ?videos?|onlyfans"
    r"|kill (?:my|him|her|them|you)\w*|murder\w*|bombs?|bombing|guns?|pistol|weapons?"
    r"|drugs?|cocaine|weed|ganja"
    r"|suicid\w*|self[- ]?harm\w*|cut myself"
    r")\b",
    re.IGNORECASE,
)

# Words that make a message about fashion even when no product field was recognised.
_FASHION = re.compile(
    r"\b(?:wear\w*|outfit\w*|style\w*|styling|look(?:s|ing)? good|lookbook|fashion\w*"
    r"|cloth\w*|attire"
    r"|dress(?:es|ed|ing)?|pair\w*|match\w*|colou?rs?|shades?|size\w*|fits?|fitting|trend\w*|vibe"
    r"|ethnic|western|traditional|formal|casual|accessor\w*|bags?|handbags?|watch(?:es)?|belts?|caps?"
    r"|hats?|sunglasses|shades|jewel\w*|earrings?|necklaces?|scarf|stole|dupatta|saree|sari|lehenga"
    r"|blazer|suit|tie|socks?|boots?|heels?|sandals?|loafers?|slippers?|flats|swimwear|bikini|lingerie"
    r"|innerwear|wardrobe|capsule|layer\w*|occasion|party|wedding|interview|date|festival|office|college)\b",
    re.IGNORECASE,
)
_REFINE = re.compile(
    r"\b(?:cheaper|costlier|expensive|budget|price|less|more|similar|another|other|different"
    r"|instead|only|without|actually|change|lighter|darker|bigger|smaller|longer|shorter)\b",
    re.IGNORECASE,
)
# "I need …", "show me …": a shopping request for something the rules don't know yet. The AI
# names the item (or finds it isn't fashion), instead of the guard turning a shopper away.
_WANTS = re.compile(
    r"\b(?:need|want|buy|shop(?:ping)?|show|find|looking for|search|get me|suggest"
    r"|chahiye|chaiye|dikhao|dikha|kharid\w*|lena)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"^\s*(?:what|which|how|should|can|could|does|do|is|are|will|would|suggest|recommend|help)\b|\?\s*$",
    re.IGNORECASE,
)


def screen(text: str, *, in_conversation: bool = False) -> Verdict:
    """Classify a message without any AI call. In a conversation about something already, a
    bare refinement ("actually under 1200", "something cheaper") is about fashion too."""
    if _UNSAFE.search(text):
        return "unsafe"
    slots = parse_request(text)
    if in_conversation and (
        slots.budget_max_paise or slots.budget_min_paise or slots.gender or _REFINE.search(text)
    ):
        return "question" if _QUESTION.search(text) else "shop"
    about_fashion = bool(
        slots.category
        or slots.occasion
        or slots.colors
        or slots.fit
        or slots.fabric
        or slots.brand
        or find_brand(text)
        or guess_category(text)
        or _FASHION.search(text)
        or (_WANTS.search(text) and unknown_words(text))
        or (slots.gender and slots.budget_max_paise)
    )
    if not about_fashion:
        return "off_topic"
    return "question" if _QUESTION.search(text) else "shop"
