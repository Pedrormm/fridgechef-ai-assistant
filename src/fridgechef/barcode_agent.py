from __future__ import annotations

from src.fridgechef.models import BarcodeObservation, FridgeAnalysis


def summarize_barcode_findings(analysis: FridgeAnalysis) -> list[str]:
    """Convert label and barcode observations into short user-facing notes."""
    notes: list[str] = []

    for observation in analysis.barcode_observations:
        if observation.barcode_text:
            notes.append(f"Código detectado: {observation.barcode_text}")
        if observation.expiry_text:
            notes.append(f"Fecha o etiqueta visible: {observation.expiry_text}")
        if observation.product_name_guess:
            notes.append(f"Producto estimado: {observation.product_name_guess}")

    if not notes:
        notes.append("No se ha detectado una etiqueta o código legible en la imagen.")

    return notes
