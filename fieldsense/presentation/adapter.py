"""Backend to UI view adapter implementation."""

from typing import Optional, Dict, List

from fieldsense.domain.models import FieldSession, SampleSource
from fieldsense.spatial import SpatialFieldResult
from fieldsense.zones import ZoneDetectionResult
from fieldsense.recommendations import RecommendationResult
from .models import (
    UIFieldView,
    FieldSummary,
    GPSStatus,
    SamplingStatus,
    HealthSummary,
    MapView,
    MapPoint,
    UIZone,
    UIRecommendation,
    SystemStatus,
)


class UIViewAdapter:
    """Transforms backend intelligence, spatial, zone, and recommendation results into UIFieldView.

    Does NOT calculate or modify soil health scores, interpolation, or recommendation logic.
    """

    def adapt(
        self,
        session: FieldSession,
        spatial: SpatialFieldResult,
        zones: ZoneDetectionResult,
        recommendations: RecommendationResult,
        expected_samples: int = 25,
    ) -> UIFieldView:
        """Adapt backend domain results to UIFieldView.

        Args:
            session: Raw FieldSession.
            spatial: SpatialFieldResult.
            zones: ZoneDetectionResult.
            recommendations: RecommendationResult.
            expected_samples: Configured target sample count.

        Returns:
            UIFieldView ready for presentation rendering.
        """
        valid_count = len(spatial.source_sample_ids)
        total_count = session.sample_count
        rejected_count = max(0, total_count - valid_count)

        # 1. Primary layer average soil health score
        soil_health_layer = spatial.layers.get("soil_health")
        valid_sh_vals = (
            [gv.value for gv in soil_health_layer.grid_values if gv.value is not None]
            if soil_health_layer
            else []
        )
        avg_sh = sum(valid_sh_vals) / len(valid_sh_vals) if valid_sh_vals else 0.0
        sh_status = self._classify_status(avg_sh)

        # 2. Field Summary
        field_summary = FieldSummary(
            field_name=session.field_name or "Field-01",
            session_id=session.session_id,
            sample_count=total_count,
            valid_sample_count=valid_count,
            rejected_sample_count=rejected_count,
            coverage_ratio=spatial.coverage.coverage_ratio,
            overall_soil_health=round(avg_sh, 2),
            soil_health_status=sh_status,
            methodology_version=spatial.methodology_version,
        )

        # 3. Data Source Determination
        sample_sources = {s.source for s in session.samples}
        source_mode = "VIRTUAL" if SampleSource.VIRTUAL in sample_sources or not sample_sources else "HARDWARE"

        # 4. GPS Status
        first_valid = next((s for s in session.samples if s.sample_id in spatial.source_sample_ids), None)
        gps_status = GPSStatus(
            available=first_valid is not None,
            latitude=first_valid.latitude if first_valid else None,
            longitude=first_valid.longitude if first_valid else None,
            status="FIXED" if first_valid else "NO_FIX",
            mode=source_mode,
        )

        # 5. Sampling Status
        sampling_status = SamplingStatus(
            total_samples=total_count,
            valid_samples=valid_count,
            rejected_samples=rejected_count,
            expected_samples=expected_samples,
            progress_ratio=round(min(1.0, valid_count / max(1, expected_samples)), 2),
        )

        # 6. Health Summary (Average scores per layer)
        health_summary = HealthSummary(
            score=round(avg_sh, 2),
            status=sh_status,
            nitrogen_score=self._layer_avg(spatial, "nitrogen"),
            moisture_score=self._layer_avg(spatial, "moisture"),
            carbon_readiness_score=self._layer_avg(spatial, "carbon_readiness"),
            evidence_level="LIMITED",
        )

        # 7. Map View & Grid Points per layer
        grid_by_layer: Dict[str, List[MapPoint]] = {}
        for layer_id, layer in spatial.layers.items():
            pts: List[MapPoint] = []
            for gp, gv in zip(spatial.grid_points, layer.grid_values):
                val_status = self._classify_status(gv.value) if gv.value is not None else "UNAVAILABLE"
                pts.append(
                    MapPoint(
                        latitude=gp.latitude,
                        longitude=gp.longitude,
                        value=round(gv.value, 3) if gv.value is not None else None,
                        support_distance=round(gv.nearest_sample_distance, 1),
                        status=val_status,
                    )
                )
            grid_by_layer[layer_id] = pts

        map_view = MapView(
            bounds=spatial.bounds.to_dict(),
            grid_by_layer=grid_by_layer,
            active_layer="soil_health",
            available_layers=list(spatial.layers.keys()),
        )

        # 8. UI Zones
        rec_counts: Dict[str, int] = {}
        for rec in recommendations.recommendations:
            rec_counts[rec.zone_id] = rec_counts.get(rec.zone_id, 0) + 1

        ui_zones: List[UIZone] = []
        for zone in zones.zones:
            ui_z = UIZone(
                zone_id=zone.zone_id,
                status=zone.status,
                severity=zone.severity,
                primary_issue=zone.primary_issue,
                affected_parameters=list(zone.affected_parameters),
                confidence=zone.confidence,
                centroid=zone.centroid,
                area_estimate=zone.area_estimate,
                recommendation_count=rec_counts.get(zone.zone_id, 0),
            )
            ui_zones.append(ui_z)

        # 9. UI Recommendations
        ui_recs: List[UIRecommendation] = []
        for rec in recommendations.recommendations:
            ui_r = UIRecommendation(
                recommendation_id=rec.recommendation_id,
                zone_id=rec.zone_id,
                category=rec.category.value if hasattr(rec.category, "value") else str(rec.category),
                priority=rec.priority.value if hasattr(rec.priority, "value") else str(rec.priority),
                action=rec.action,
                reason=rec.reason,
                confidence=rec.confidence,
            )
            ui_recs.append(ui_r)

        # 10. System Status
        system_status = SystemStatus(
            application_status="READY",
            data_source=source_mode,
            processing_status="COMPLETE",
            offline_mode=True,
        )

        return UIFieldView(
            field=field_summary,
            gps_status=gps_status,
            sampling_status=sampling_status,
            health_summary=health_summary,
            map=map_view,
            zones=ui_zones,
            recommendations=ui_recs,
            system_status=system_status,
        )

    def _layer_avg(self, spatial: SpatialFieldResult, layer_id: str) -> float:
        """Calculate average score for a given spatial layer."""
        layer = spatial.layers.get(layer_id)
        if not layer:
            return 0.0
        vals = [gv.value for gv in layer.grid_values if gv.value is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def _classify_status(self, score: float) -> str:
        """Map score to status indicator."""
        if score >= 0.70:
            return "HEALTHY"
        elif score >= 0.40:
            return "MODERATE"
        else:
            return "POOR"
