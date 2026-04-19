"""Translator package."""
from cer_intent.translators.capacity_translator import CapacityTranslator
from cer_intent.translators.qos_translator import QoSTranslator
from cer_intent.translators.modulation_translator import ModulationTranslator
from cer_intent.translators.resilience_translator import ResilienceTranslator
from cer_intent.translators.slice_translator import SliceTranslator
from cer_intent.intent_schema import IntentType

TRANSLATOR_MAP = {
    IntentType.CAPACITY:   CapacityTranslator,
    IntentType.QOS:        QoSTranslator,
    IntentType.MODULATION: ModulationTranslator,
    IntentType.RESILIENCE: ResilienceTranslator,
    IntentType.SLICE:      SliceTranslator,
}


def get_translator(intent_type: IntentType):
    cls = TRANSLATOR_MAP.get(intent_type)
    if cls is None:
        raise ValueError(f"No translator registered for intent type: {intent_type}")
    return cls()
