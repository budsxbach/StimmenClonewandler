"""Hilfsmittel für Tests: Erzeugt eine *Teststimme* im Piper-Format.

WICHTIG: Das ist **keine echte Stimme**. Das Modell gibt nur einen einfachen
Ton aus, dessen Länge von der Anzahl der Phoneme und vom Sprechtempo abhängt.
Es dient ausschließlich dazu, die technische Kette der App (Phonemisierung,
ONNX-Sitzung, Audiozusammensetzung, Klangformung, WAV-Ausgabe, Fortschritt)
ohne großen Download zu prüfen.

Die Datei landet im Test-Datenordner, niemals im Projekt-Git.
Benötigt das optionale Paket `onnx` (nur für Tests).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def build_test_voice(target_dir: Path, *, name: str = "de_DE-test-ton-medium", sample_rate: int = 22050) -> Path:
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    from piper.phoneme_ids import DEFAULT_PHONEME_ID_MAP

    target_dir.mkdir(parents=True, exist_ok=True)
    model_path = target_dir / f"{name}.onnx"

    # ---- Graph: Audio-Länge ~ input_lengths * length_scale * 512 ----------
    inp = helper.make_tensor_value_info("input", TensorProto.INT64, [1, None])
    in_len = helper.make_tensor_value_info("input_lengths", TensorProto.INT64, [1])
    scales = helper.make_tensor_value_info("scales", TensorProto.FLOAT, [3])
    out = helper.make_tensor_value_info("audio", TensorProto.FLOAT, [1, 1, None])

    initializers = [
        numpy_helper.from_array(np.array([1, 1], dtype=np.int64), "ones_shape"),
        numpy_helper.from_array(np.array([512], dtype=np.int64), "hop"),
        numpy_helper.from_array(np.array([1], dtype=np.int64), "slice_start"),
        numpy_helper.from_array(np.array([2], dtype=np.int64), "slice_end"),
        numpy_helper.from_array(np.array([0], dtype=np.int64), "slice_axis"),
        numpy_helper.from_array(np.array([-1], dtype=np.int64), "reshape_shape"),
        numpy_helper.from_array(np.array([0], dtype=np.int64), "range_start"),
        numpy_helper.from_array(np.array([1], dtype=np.int64), "range_delta"),
        # 95 Hz bei 22.050 Hz: Bogenmaß pro Sample = 2*pi*f/rate
        numpy_helper.from_array(np.array(2 * np.pi * 95.0 / sample_rate, dtype=np.float32), "freq"),
        numpy_helper.from_array(np.array(0.35, dtype=np.float32), "amp"),
        numpy_helper.from_array(np.array(2.5, dtype=np.float32), "length_bias"),
    ]

    nodes = [
        # Länge in Samples: input_lengths * 512 / length_scale
        helper.make_node("Cast", ["input_lengths"], ["len_f"], to=TensorProto.FLOAT),
        helper.make_node("Slice", ["scales", "slice_start", "slice_end", "slice_axis"], ["ls"]),
        helper.make_node("Mul", ["len_f", "length_bias"], ["len_scaled"]),
        helper.make_node("Mul", ["len_scaled", "ls"], ["samples_f"]),
        helper.make_node("Cast", ["samples_f"], ["samples_i"], to=TensorProto.INT64),
        helper.make_node("Mul", ["samples_i", "hop"], ["total"]),
        helper.make_node("Concat", ["ones_shape", "total"], ["shape"], axis=0),
        helper.make_node("ConstantOfShape", ["shape"], ["zeros"]),
        # Zeitachse 0..T-1
        helper.make_node("Squeeze", ["total"], ["total_scalar"]),
        helper.make_node("Range", ["range_start", "total_scalar", "range_delta"], ["idx"]),
        helper.make_node("Cast", ["idx"], ["idx_f"], to=TensorProto.FLOAT),
        helper.make_node("Mul", ["idx_f", "freq"], ["phase"]),
        helper.make_node("Sin", ["phase"], ["wave"]),
        helper.make_node("Mul", ["wave", "amp"], ["tone"]),
        helper.make_node("Reshape", ["tone", "reshape_shape"], ["audio"]),
    ]

    graph = helper.make_graph(nodes, "test_voice", [inp, in_len, scales], [out], initializers)
    # Smarte Ausgaben: die Form von "audio" ist [1, 1, -1]
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.checker.check_model(model)
    onnx.save(model, str(model_path))

    config = {
        "num_symbols": len(DEFAULT_PHONEME_ID_MAP),
        "num_speakers": 1,
        "audio": {"sample_rate": sample_rate},
        "espeak": {"voice": "de"},
        "language": {"code": "de_DE", "family": "de", "name": "German"},
        "phoneme_type": "espeak",
        "phoneme_id_map": DEFAULT_PHONEME_ID_MAP,
        "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
        "dataset": "test-ton (kein echtes Sprachmodell)",
        "piper_version": "1.8.0",
    }
    (target_dir / f"{name}.onnx.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return model_path
