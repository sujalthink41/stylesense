import pytest

from stylesense.modules.stylist.guard import screen


@pytest.mark.parametrize(
    "text",
    [
        "asics shoes for men",
        "black jeans for my girlfriend under 1500",
        "kurta for a sangeet",
        "something for my cousin's haldi",
        "linen shirt",
        "bikini for goa",  # swimwear is fashion
        "Bombay Denim Co. Men Maroon Slim T-Shirt",  # a brand, not a bomb
        "gunmetal grey jacket",
        "nude heels for a party",  # a colour
    ],
)
def test_shopping_requests_are_allowed(text: str) -> None:
    assert screen(text) == "shop"


@pytest.mark.parametrize(
    "text",
    [
        "what goes with black jeans?",
        "what should I wear to a beach wedding",
        "how do I style an oversized shirt",
        "which colour suits dark skin?",
    ],
)
def test_fashion_questions_get_an_answer(text: str) -> None:
    assert screen(text) == "question"


@pytest.mark.parametrize(
    "text",
    [
        "what is the capital of france?",
        "write my homework",
        "tell me a joke",
        "hmmm",
        "asdkjh qwe",
    ],
)
def test_anything_else_is_politely_redirected(text: str) -> None:
    assert screen(text) == "off_topic"


@pytest.mark.parametrize(
    "text",
    [
        "you are a f*cking idiot".replace("*", "u"),
        "chutiya app",
        "show me nude photos",
        "where can I buy a gun",
    ],
)
def test_abuse_and_unsafe_requests_are_refused(text: str) -> None:
    assert screen(text) == "unsafe"


@pytest.mark.parametrize("text", ["actually under 1200", "something cheaper", "only for women"])
def test_refinements_are_allowed_inside_a_conversation(text: str) -> None:
    assert screen(text, in_conversation=True) == "shop"
    assert screen(text) == "off_topic"  # on their own they aren't about anything yet


def test_gibberish_is_redirected_even_inside_a_conversation() -> None:
    assert screen("hmmm", in_conversation=True) == "off_topic"
