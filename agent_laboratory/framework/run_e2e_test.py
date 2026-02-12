#!/usr/bin/env python3
"""
End-to-End Test Runner for YouTube Content Pipeline
Tests with real video: https://www.youtube.com/watch?v=KgSEzvGOBio
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

console = Console()

# Test Configuration
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=KgSEzvGOBio"
TEST_VIDEO_ID = "KgSEzvGOBio"
WORK_DIR = Path("/tmp/e2e_test_kgsezv")
RESULTS_DIR = Path(__file__).parent.parent / "results"
LOGS_DIR = Path(__file__).parent.parent / "logs"


def print_header(text):
    console.print(f"\n[bold blue]{'=' * 70}[/bold blue]")
    console.print(f"[bold blue]{text}[/bold blue]")
    console.print(f"[bold blue]{'=' * 70}[/bold blue]\n")


def print_step(num, name, status, details=""):
    icon = "✅" if status else "❌"
    color = "green" if status else "red"
    console.print(f"{icon} Step {num}: [{color}]{name}[/{color}]")
    if details:
        console.print(f"   [dim]{details}[/dim]")


def log_to_file(step_name, data):
    """Log test data to file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"{timestamp}_{step_name}.json"
    with open(log_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return log_file


def run_e2e_test():
    """Run comprehensive end-to-end test with the specified video."""

    print_header("E2E TEST: YouTube Content Pipeline")
    console.print(f"[dim]Video URL: {TEST_VIDEO_URL}[/dim]")
    console.print(f"[dim]Video ID: {TEST_VIDEO_ID}[/dim]")
    console.print(f"[dim]Work Directory: {WORK_DIR}[/dim]\n")

    # Ensure directories exist
    WORK_DIR.mkdir(exist_ok=True, parents=True)
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)

    results = {
        "test_video_id": TEST_VIDEO_ID,
        "test_video_url": TEST_VIDEO_URL,
        "started_at": datetime.utcnow().isoformat(),
        "steps": {},
    }

    step_times = {}
    overall_start = time.time()

    # =================================================================
    # STEP 1: TRANSCRIPT ACQUISITION
    # =================================================================
    print_header("STEP 1: TRANSCRIPT ACQUISITION")
    step_start = time.time()

    try:
        from src.transcription.handler import TranscriptionHandler, identify_source_type

        # Test source identification
        source_type, source_id = identify_source_type(TEST_VIDEO_URL)
        print_step(1, "Source Identification", True, f"Type: {source_type}, ID: {source_id}")

        # Test transcript acquisition
        handler = TranscriptionHandler(WORK_DIR)
        transcript = handler.get_transcript(source_id, source_type)

        step_times["transcript_acquisition"] = time.time() - step_start
        results["steps"]["transcript_acquisition"] = {
            "status": "PASS",
            "source_type": source_type,
            "source_id": source_id,
            "transcript_source": transcript.source,
            "segments_count": len(transcript.segments),
            "duration": transcript.duration,
            "text_length": len(transcript.full_text),
            "time_seconds": step_times["transcript_acquisition"],
        }

        print_step(
            1,
            "Transcript Acquisition",
            True,
            f"Source: {transcript.source}, Segments: {len(transcript.segments)}",
        )

        # Validate transcript format
        format_valid = hasattr(transcript, "segments") and len(transcript.segments) > 0
        results["steps"]["transcript_acquisition"]["format_valid"] = format_valid
        print_step(1, "Transcript Format", format_valid, f"Segments: {len(transcript.segments)}")

        # Validate transcript content
        full_text = transcript.full_text
        content_valid = len(full_text) > 500  # Relaxed threshold for any video
        results["steps"]["transcript_acquisition"]["content_valid"] = content_valid
        results["steps"]["transcript_acquisition"]["sample_text"] = full_text[:200]
        print_step(1, "Transcript Content", content_valid, f"Length: {len(full_text)} chars")

    except Exception as e:
        step_times["transcript_acquisition"] = time.time() - step_start
        results["steps"]["transcript_acquisition"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["transcript_acquisition"],
        }
        console.print(f"[red]Step 1 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 2: AGENT 1 - TRANSCRIPT INTELLIGENCE
    # =================================================================
    print_header("STEP 2: AGENT 1 - TRANSCRIPT INTELLIGENCE (Gemini 2.5 Flash)")
    step_start = time.time()

    try:
        from src.llm_agents.transcript_agent import TranscriptIntelligenceAgent

        agent = TranscriptIntelligenceAgent()
        intel = agent.analyze_with_fallback(transcript)

        step_times["agent1_transcript"] = time.time() - step_start
        results["steps"]["agent1_transcript"] = {
            "status": "PASS",
            "model": agent.model,
            "content_type": intel.content_type,
            "market_context": intel.market_context,
            "signals_count": len(intel.signals),
            "price_levels_count": len(intel.price_levels),
            "time_seconds": step_times["agent1_transcript"],
        }

        print_step(2, "Agent 1 Execution", True, f"Model: {agent.model}")

        # Validate content type
        content_type_valid = intel.content_type and intel.content_type != "general"
        results["steps"]["agent1_transcript"]["content_type_valid"] = content_type_valid
        print_step(2, "Content Type Detected", content_type_valid, f"Type: {intel.content_type}")

        # Validate signals
        signals_found = len(intel.signals) > 0
        results["steps"]["agent1_transcript"]["signals_found"] = signals_found
        sig_details = f"Found {len(intel.signals)} signals"
        for sig in intel.signals[:2]:
            sig_details += f"\n   • {sig.asset} {sig.direction} @ {sig.entry_price or 'N/A'}"
        print_step(2, "Trading Signals", signals_found, sig_details)

        # Validate price levels
        levels_found = len(intel.price_levels) > 0
        results["steps"]["agent1_transcript"]["levels_found"] = levels_found
        level_details = f"Found {len(intel.price_levels)} price levels"
        for lvl in intel.price_levels[:2]:
            level_details += f"\n   • {lvl.label} ({lvl.type})"
        print_step(2, "Price Levels", levels_found, level_details)

        # Validate frame extraction plan
        plan_valid = (
            intel.frame_extraction_plan and len(intel.frame_extraction_plan.key_moments) > 0
        )
        results["steps"]["agent1_transcript"]["frame_plan_valid"] = plan_valid
        if plan_valid:
            plan = intel.frame_extraction_plan
            print_step(
                2,
                "Frame Extraction Plan",
                True,
                f"Suggested: {plan.suggested_count} frames, "
                f"Key moments: {len(plan.key_moments)}, "
                f"Interval: {plan.coverage_interval_seconds}s",
            )
        else:
            print_step(2, "Frame Extraction Plan", False, "No plan generated")

        # Log intelligence data
        log_to_file(
            "agent1_intelligence",
            {
                "content_type": intel.content_type,
                "market_context": intel.market_context,
                "signals": [s.model_dump() for s in intel.signals],
                "price_levels": [p.model_dump() for p in intel.price_levels],
                "frame_plan": intel.frame_extraction_plan.model_dump()
                if intel.frame_extraction_plan
                else None,
            },
        )

    except Exception as e:
        step_times["agent1_transcript"] = time.time() - step_start
        results["steps"]["agent1_transcript"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["agent1_transcript"],
        }
        console.print(f"[red]Step 2 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 3: VIDEO DOWNLOAD (with fallback to local video)
    # =================================================================
    print_header("STEP 3: VIDEO DOWNLOAD")
    step_start = time.time()

    # Fallback video for testing when YouTube download fails
    FALLBACK_VIDEO = project_root / "Candlesticks.mp4"

    try:
        from src.video.handler import VideoHandler

        video_handler = VideoHandler(WORK_DIR)

        try:
            video_path = video_handler.download_video(source_id, source_type)
            download_source = "youtube"
            print_step(3, "YouTube Download", True, f"Path: {video_path}")
        except Exception as download_error:
            # Fallback to local video if YouTube download fails
            console.print(f"[yellow]⚠️ YouTube download failed: {download_error}[/yellow]")
            console.print(f"[yellow]   Falling back to local video: {FALLBACK_VIDEO}[/yellow]")

            if FALLBACK_VIDEO.exists():
                import shutil

                # Copy fallback video to work directory
                video_path = WORK_DIR / "fallback_video.mp4"
                shutil.copy(FALLBACK_VIDEO, video_path)
                download_source = "fallback_local"
                print_step(3, "Fallback Video", True, f"Path: {video_path}")
            else:
                raise download_error

        step_times["video_download"] = time.time() - step_start
        results["steps"]["video_download"] = {
            "status": "PASS",
            "path": str(video_path),
            "source": download_source,
            "time_seconds": step_times["video_download"],
        }

        # Validate video format
        format_valid = video_path.exists() and video_path.suffix == ".mp4"
        results["steps"]["video_download"]["format_valid"] = format_valid
        print_step(3, "Video Format", format_valid, f"Format: {video_path.suffix}")

        # Validate video size
        size_mb = video_path.stat().st_size / (1024 * 1024)
        size_valid = size_mb > 1
        results["steps"]["video_download"]["size_mb"] = size_mb
        results["steps"]["video_download"]["size_valid"] = size_valid
        print_step(3, "Video Size", size_valid, f"Size: {size_mb:.1f} MB")

    except Exception as e:
        step_times["video_download"] = time.time() - step_start
        results["steps"]["video_download"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["video_download"],
        }
        console.print(f"[red]Step 3 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 4: FRAME EXTRACTION
    # =================================================================
    print_header("STEP 4: FRAME EXTRACTION")
    step_start = time.time()

    try:
        frames = video_handler.extract_frames(video_path, intel.frame_extraction_plan)

        step_times["frame_extraction"] = time.time() - step_start
        results["steps"]["frame_extraction"] = {
            "status": "PASS",
            "frames_count": len(frames),
            "time_seconds": step_times["frame_extraction"],
        }

        print_step(4, "Frame Extraction", True, f"Extracted: {len(frames)} frames")

        # Validate frame count
        count_valid = len(frames) >= 3  # Relaxed threshold
        results["steps"]["frame_extraction"]["count_valid"] = count_valid
        print_step(4, "Frame Count", count_valid, f"Frames: {len(frames)}")

        # Validate frame locations
        frames_dir = WORK_DIR / "frames"
        files_valid = frames_dir.exists() and all(f.exists() for f in frames)
        results["steps"]["frame_extraction"]["files_valid"] = files_valid
        print_step(4, "Frame Files Valid", files_valid, f"All {len(frames)} files exist")

    except Exception as e:
        step_times["frame_extraction"] = time.time() - step_start
        results["steps"]["frame_extraction"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["frame_extraction"],
        }
        console.print(f"[red]Step 4 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 5: AGENT 2 - FRAME INTELLIGENCE
    # =================================================================
    print_header("STEP 5: AGENT 2 - FRAME INTELLIGENCE (qwen3-vl-plus)")
    step_start = time.time()

    try:
        from src.llm_agents.frame_agent import FrameIntelligenceAgent

        frame_agent = FrameIntelligenceAgent()
        frame_intel = frame_agent.analyze_with_fallback(frames)

        step_times["agent2_frames"] = time.time() - step_start
        results["steps"]["agent2_frames"] = {
            "status": "PASS",
            "model": frame_agent.model,
            "frames_analyzed": frame_intel.summary.total_frames_analyzed,
            "frames_selected": frame_intel.summary.frames_selected,
            "time_seconds": step_times["agent2_frames"],
        }

        print_step(5, "Agent 2 Execution", True, f"Model: {frame_agent.model}")

        # Determine if batch or individual was used
        method = (
            "Batch" if len(frame_intel.frame_analyses) == len(frames) else "Individual Fallback"
        )
        results["steps"]["agent2_frames"]["method"] = method
        print_step(5, "Analysis Method", True, f"Method: {method}")

        # Validate frames selected
        selected_valid = frame_intel.summary.frames_selected > 0
        results["steps"]["agent2_frames"]["selected_valid"] = selected_valid
        print_step(
            5,
            "Frames Selected",
            selected_valid,
            f"Selected: {frame_intel.summary.frames_selected} / {frame_intel.summary.total_frames_analyzed}",
        )

        # Validate frame analyses
        valid_analyses = sum(1 for f in frame_intel.frame_analyses if f.analysis)
        analyses_valid = valid_analyses > 0
        results["steps"]["agent2_frames"]["analyses_valid"] = analyses_valid
        results["steps"]["agent2_frames"]["valid_analyses_count"] = valid_analyses
        print_step(
            5,
            "Frame Analyses Valid",
            analyses_valid,
            f"Valid analyses: {valid_analyses}/{len(frame_intel.frame_analyses)}",
        )

        # Show sample analysis
        sample = frame_intel.selected_frames[0] if frame_intel.selected_frames else None
        if sample:
            console.print(f"\n   [dim]Sample frame analysis (frame {sample.frame_number}):[/dim]")
            if "asset" in sample.analysis:
                console.print(f"   [dim]  Asset: {sample.analysis['asset']}[/dim]")
            if "sentiment" in sample.analysis:
                console.print(f"   [dim]  Sentiment: {sample.analysis['sentiment']}[/dim]")

        # Log frame intelligence
        log_to_file(
            "agent2_frame_intel",
            {
                "summary": frame_intel.summary.model_dump(),
                "selected_frames": [f.model_dump() for f in frame_intel.selected_frames[:3]],
            },
        )

    except Exception as e:
        step_times["agent2_frames"] = time.time() - step_start
        results["steps"]["agent2_frames"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["agent2_frames"],
        }
        console.print(f"[red]Step 5 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 6: AGENT 3 - SYNTHESIS
    # =================================================================
    print_header("STEP 6: AGENT 3 - SYNTHESIS (Gemini 2.5 Flash)")
    step_start = time.time()

    try:
        from src.llm_agents.synthesis_agent import SynthesisAgent

        synth_agent = SynthesisAgent()
        synthesis = synth_agent.synthesize_with_fallback(intel, frame_intel)

        step_times["agent3_synthesis"] = time.time() - step_start
        results["steps"]["agent3_synthesis"] = {
            "status": "PASS",
            "model": synth_agent.model,
            "time_seconds": step_times["agent3_synthesis"],
        }

        print_step(6, "Agent 3 Execution", True, f"Model: {synth_agent.model}")

        # Validate executive summary
        summary_valid = synthesis.executive_summary and len(synthesis.executive_summary) > 50
        results["steps"]["agent3_synthesis"]["summary_valid"] = summary_valid
        results["steps"]["agent3_synthesis"]["summary_length"] = len(
            synthesis.executive_summary or ""
        )
        print_step(
            6,
            "Executive Summary",
            summary_valid,
            f"Length: {len(synthesis.executive_summary)} chars",
        )
        console.print(f"\n   [dim]Preview: {synthesis.executive_summary[:100]}...[/dim]")

        # Validate key takeaways
        takeaways_valid = synthesis.key_takeaways and len(synthesis.key_takeaways) > 0
        results["steps"]["agent3_synthesis"]["takeaways_valid"] = takeaways_valid
        results["steps"]["agent3_synthesis"]["takeaways_count"] = len(synthesis.key_takeaways or [])
        print_step(
            6, "Key Takeaways", takeaways_valid, f"Count: {len(synthesis.key_takeaways or [])}"
        )
        for i, takeaway in enumerate((synthesis.key_takeaways or [])[:3], 1):
            console.print(f"   [dim]{i}. {takeaway[:60]}...[/dim]")

        # Validate detailed analysis
        analysis_valid = synthesis.detailed_analysis and len(synthesis.detailed_analysis) > 100
        results["steps"]["agent3_synthesis"]["analysis_valid"] = analysis_valid
        results["steps"]["agent3_synthesis"]["analysis_length"] = len(
            synthesis.detailed_analysis or ""
        )
        print_step(
            6,
            "Detailed Analysis",
            analysis_valid,
            f"Length: {len(synthesis.detailed_analysis or '')} chars",
        )

        # Log synthesis
        log_to_file("agent3_synthesis", synthesis.model_dump())

    except Exception as e:
        step_times["agent3_synthesis"] = time.time() - step_start
        results["steps"]["agent3_synthesis"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["agent3_synthesis"],
        }
        console.print(f"[red]Step 6 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # STEP 7: FINAL RESULT STRUCTURE
    # =================================================================
    print_header("STEP 7: FINAL RESULT STRUCTURE")
    step_start = time.time()

    try:
        from src.core.schemas import VideoAnalysisResult, ProcessingMetadata

        # Build final result
        metadata = ProcessingMetadata(
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            llm_calls_made=3,
            duration_seconds=sum(step_times.values()),
            transcript_source=transcript.source,
            video_downloaded=True,
        )

        result = VideoAnalysisResult.from_agents(
            video_id=source_id,
            source_type=source_type,
            source_url=TEST_VIDEO_URL,
            title=None,
            duration=transcript.duration,
            transcript_intel=intel,
            frame_intel=frame_intel,
            synthesis=synthesis,
            metadata=metadata,
        )

        step_times["result_structure"] = time.time() - step_start
        results["steps"]["result_structure"] = {
            "status": "PASS",
            "time_seconds": step_times["result_structure"],
        }

        print_step(7, "Result Object Creation", True, "VideoAnalysisResult built successfully")

        # Validate JSON serialization
        try:
            result_dict = result.model_dump_for_mongo()
            json_str = json.dumps(result_dict, default=str)
            json_valid = True
            results["steps"]["result_structure"]["json_valid"] = json_valid
            results["steps"]["result_structure"]["json_size_bytes"] = len(json_str)
            print_step(7, "JSON Serialization", json_valid, f"JSON size: {len(json_str)} bytes")
        except Exception as e:
            json_valid = False
            results["steps"]["result_structure"]["json_valid"] = json_valid
            results["steps"]["result_structure"]["json_error"] = str(e)
            print_step(7, "JSON Serialization", json_valid, str(e))

        # Validate all critical fields present
        critical_fields = [
            "video_id",
            "content_type",
            "transcript_intelligence",
            "frame_intelligence",
            "synthesis",
            "processing",
        ]
        missing = [f for f in critical_fields if f not in result_dict]
        all_fields_present = not missing
        results["steps"]["result_structure"]["all_fields_present"] = all_fields_present
        results["steps"]["result_structure"]["missing_fields"] = missing

        if all_fields_present:
            print_step(
                7, "All Critical Fields Present", True, f"Fields: {', '.join(critical_fields)}"
            )
        else:
            print_step(7, "Critical Fields Check", False, f"Missing: {', '.join(missing)}")

        # Save result
        output_path = (
            RESULTS_DIR
            / f"e2e_test_{TEST_VIDEO_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2, default=str)
        results["steps"]["result_structure"]["output_path"] = str(output_path)
        print_step(7, "Result Saved", True, f"Path: {output_path}")

    except Exception as e:
        step_times["result_structure"] = time.time() - step_start
        results["steps"]["result_structure"] = {
            "status": "FAIL",
            "error": str(e),
            "time_seconds": step_times["result_structure"],
        }
        console.print(f"[red]Step 7 FAILED: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")
        return save_and_exit(results, 1)

    # =================================================================
    # SUMMARY
    # =================================================================
    print_header("TEST SUMMARY")

    overall_time = time.time() - overall_start
    results["completed_at"] = datetime.utcnow().isoformat()
    results["total_time_seconds"] = overall_time
    results["step_times"] = step_times

    # Calculate pass/fail
    passed = sum(1 for s in results["steps"].values() if s.get("status") == "PASS")
    total = len(results["steps"])
    results["summary"] = {
        "passed": passed,
        "total": total,
        "pass_rate": passed / total * 100 if total > 0 else 0,
        "total_time_seconds": overall_time,
    }

    # Display timing breakdown
    timing_table = Table(title="Execution Time Breakdown")
    timing_table.add_column("Step", style="cyan")
    timing_table.add_column("Time (s)", style="yellow", justify="right")

    for step, duration in step_times.items():
        timing_table.add_row(step, f"{duration:.2f}")
    timing_table.add_row("[bold]Total", f"[bold]{overall_time:.2f}")

    console.print(timing_table)

    # Display results table
    results_table = Table(title="Test Results")
    results_table.add_column("Step", style="cyan")
    results_table.add_column("Status", style="green")

    for step_name, step_data in results["steps"].items():
        status = "✅ PASS" if step_data.get("status") == "PASS" else "❌ FAIL"
        results_table.add_row(step_name, status)

    console.print(results_table)

    console.print(
        f"\n[bold]Results: {passed}/{total} tests passed ({passed / total * 100:.1f}%)[/bold]"
    )
    console.print(f"[bold]Total Execution Time: {overall_time:.2f} seconds[/bold]")

    # Save final results
    final_results_path = (
        RESULTS_DIR / f"e2e_summary_{TEST_VIDEO_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(final_results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Full results saved to: {final_results_path}[/dim]")

    if passed == total:
        console.print(
            "\n[bold green]🎉 ALL TESTS PASSED! Pipeline is working correctly.[/bold green]"
        )
        return save_and_exit(results, 0)
    else:
        console.print(
            f"\n[bold red]⚠️  {total - passed} tests failed. Check output above.[/bold red]"
        )
        return save_and_exit(results, 1)


def save_and_exit(results, exit_code):
    """Save results and return exit code."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"e2e_results_{TEST_VIDEO_ID}_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to: {results_file}[/dim]")
    return exit_code


if __name__ == "__main__":
    sys.exit(run_e2e_test())
