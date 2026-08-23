"""FieldSense AI V1 — Live Hardware Integration Runner.

Executes unified hardware acquisition path:
Real JXBS + Real GPS -> HardwareSensorAdapter -> FieldSample -> ValidationEngine -> FieldIntelligenceEngine
"""

import sys
from fieldsense.hardware.factory import SensorAdapterFactory, DataSourceConfig
from fieldsense.intelligence import ValidationEngine, FieldIntelligenceEngine


def run_live_hardware_test() -> None:
    """Acquire one real hardware sample and pass through frozen Phase 1 intelligence pipeline."""
    print("\n==================================================")
    print("      FIELDSENSE V1 — LIVE HARDWARE INTEGRATION   ")
    print("==================================================")

    # 1. Initialize Hardware Sensor Adapter
    print("\n[1/5] Initializing Hardware Adapters...")
    adapter = SensorAdapterFactory.create_adapter(DataSourceConfig(source="HARDWARE"))

    try:
        # 2. Acquire Live FieldSample
        print("[2/5] Acquiring Live Hardware Sample...")
        sample = adapter.acquire_sample()

        # 3. Print Hardware Telemetry
        print(f"\n--- GPS TELEMETRY ---")
        print(f"Latitude:    {sample.latitude:.7f}°")
        print(f"Longitude:   {sample.longitude:.7f}°")

        print(f"\n--- SOIL SENSOR TELEMETRY ---")
        print(f"Nitrogen:    {sample.nitrogen} mg/kg")
        print(f"Phosphorus:  {sample.phosphorus} mg/kg")
        print(f"Potassium:   {sample.potassium} mg/kg")
        print(f"pH:          {sample.ph} pH")
        print(f"EC:          {sample.ec} µS/cm")
        print(f"Moisture:    {sample.moisture} %RH")
        print(f"Temperature: {sample.temperature} °C")

        # 4. Print FieldSample Contract
        print(f"\n--- CANONICAL FIELDSAMPLE CONTRACT ---")
        print(f"Sample ID:        {sample.sample_id}")
        print(f"Timestamp:        {sample.timestamp}")
        print(f"Source:           {sample.source.value}")
        print(f"Quality Score:    {sample.measurement_quality}")
        print(f"Validation State: {sample.validation_state.value}")

        # 5. Execute Phase 1 Validation Engine
        print("\n[3/5] Executing Phase 1 Validation Engine...")
        val_engine = ValidationEngine()
        val_result = val_engine.validate(sample)
        print(f"Validation State: {val_result.state.value}")
        print(f"Pipeline Eligible: {val_result.pipeline_eligible}")
        if val_result.reasons:
            print(f"Reasons:           {[r.value for r in val_result.reasons]}")

        if not val_result.pipeline_eligible:
            print("\n❌ Live hardware sample failed validation eligibility check.")
            sys.exit(1)

        # 6. Execute Phase 1 Intelligence Engine
        print("\n[4/5] Executing Phase 1 Intelligence Engine...")
        intel_engine = FieldIntelligenceEngine()
        intel_result = intel_engine.process(sample, val_result)

        print("\n--- PHASE 1 INTELLIGENCE RESULTS ---")
        print(f"Soil Health Score:      {intel_result.soil_health.score:.4f} ({intel_result.soil_health.score * 100:.1f}%)")
        print(f"Nitrogen Score:         {intel_result.nitrogen.score:.4f}")
        print(f"Moisture Score:         {intel_result.moisture.score:.4f}")
        print(f"Carbon Readiness Score: {intel_result.carbon_readiness.score:.4f}")
        print(f"Methodology Version:    v{intel_result.methodology_version}")

        print("\n==================================================")
        print(" SUCCESS: Hardware -> FieldSample -> Phase 1 PASS ")
        print("==================================================\n")

    finally:
        adapter.shutdown()


if __name__ == "__main__":
    run_live_hardware_test()
