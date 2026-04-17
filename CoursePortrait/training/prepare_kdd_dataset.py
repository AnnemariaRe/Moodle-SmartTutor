import pandas as pd
import numpy as np
from pathlib import Path


def prepare_kdd_dataset(input_path: str, output_file: str, max_enrollments: int = None):
    """
    Converts KDD Cup 2015 dataset into training format.
    """
    print("Preparing data from KDD Cup 2015")
    print()

    input_path_obj = Path(input_path)

    if input_path_obj.is_dir():
        actions_file = input_path_obj / "mooc_actions.tsv"
        labels_file = input_path_obj / "mooc_action_labels.tsv"

        if not actions_file.exists():
            print(f"Error: file {actions_file} not found in directory {input_path}")
            return None

        print(f"Reading data from directory {input_path}...")
        print(f"  Using file: {actions_file}")

        try:
            # Read mooc_actions.tsv: ACTIONID, USERID, TARGETID, TIMESTAMP
            df = pd.read_csv(
                actions_file,
                sep='\t'
            )

            if labels_file.exists():
                labels_df = pd.read_csv(labels_file, sep='\t')
                df = df.merge(labels_df, on='ACTIONID', how='left')
                print(f"  Loaded labels from {labels_file}")

            df = df.rename(columns={
                'USERID': 'enrollment_id',
                'TARGETID': 'object',
                'TIMESTAMP': 'time'
            })

            df['course_id'] = df['enrollment_id'] % 100
            df['source'] = 'server'
            df['event'] = 'access'
            df['username'] = 'user_' + df['enrollment_id'].astype(str)

        except Exception as e:
            print(f"Error reading files: {e}")
            print("\nTry a different format or check the file structure")
            return None

    elif input_path_obj.is_file():
        print(f"Reading data from {input_path}...")

        try:
            df = pd.read_csv(
                input_path,
                sep='\t',
                header=None,
                names=['enrollment_id', 'username', 'course_id', 'time', 'source', 'event', 'object']
            )
        except Exception as e:
            print(f"Error reading file: {e}")
            print("\nTry a different format or check the file structure")
            return None
    else:
        print(f"Error: path {input_path} not found")
        return None

    print(f"  Loaded {len(df)} records")

    df = df.sort_values(['enrollment_id', 'time'])

    if max_enrollments:
        unique_enrollments = df['enrollment_id'].unique()[:max_enrollments]
        df = df[df['enrollment_id'].isin(unique_enrollments)]
        print(f"  Limited to {max_enrollments} enrollments")

    print("\nAggregating data by enrollment and sessions...")

    aggregated = []
    enrollment_count = 0

    if df['time'].dtype == 'object':
        df['time_numeric'] = pd.to_datetime(df['time'], errors='coerce').astype('int64') / 1e9
    else:
        df['time_numeric'] = df['time']

    for enrollment_id, group in df.groupby('enrollment_id'):
        enrollment_count += 1
        if enrollment_count % 1000 == 0:
            print(f"  Processed {enrollment_count} enrollments, created {len(aggregated)} records...")

        course_id = group['course_id'].iloc[0]
        group = group.sort_values('time_numeric').reset_index(drop=True)

        time_diffs = group['time_numeric'].diff().fillna(0)
        session_breaks = (time_diffs > 1800) | (time_diffs < 0)
        session_ids = session_breaks.cumsum()

        for session_id, session_group in group.groupby(session_ids):
            if len(session_group) < 1:
                continue

            events = session_group['event'].values
            time_numeric = session_group['time_numeric'].values

            if len(time_numeric) < 2:
                duration_seconds = 10.0
            else:
                duration_seconds = float(time_numeric.max() - time_numeric.min())

            duration_ms = duration_seconds * 1000

            if duration_ms < 100 or duration_ms > 7200000:
                continue

            total_events = len(events)
            video_events = (events == 'video').sum()
            problem_events = (events == 'problem').sum()
            access_events = (events == 'access').sum()

            if video_events > 0:
                # If there are video events, use their proportion
                base_watch = video_events / max(total_events, 1)
                # Add slight variation based on duration
                duration_factor = min(1.0, duration_ms / 300000.0)  # 5 min = 100%
                watch_percent = min(1.0, base_watch * 0.7 + duration_factor * 0.3)
            else:
                # For non-video modules: combination of duration and activity
                duration_factor = min(1.0, duration_ms / 180000.0)  # 3 min = 100%
                activity_factor = min(1.0, total_events / 20.0)  # 20 events = 100%
                watch_percent = min(1.0, (duration_factor * 0.6 + activity_factor * 0.4))
                watch_percent = max(0.05, watch_percent)  # Minimum 5%

            # Add small random variation for diversity (+/-5%)
            watch_percent = np.clip(watch_percent + np.random.uniform(-0.05, 0.05), 0.0, 1.0)

            step = min(session_id + 1, 50)

            # Improved dropout logic with more balanced distribution
            if 'LABEL' in session_group.columns:
                # Use labels from the dataset
                labels = session_group['LABEL'].dropna()
                if len(labels) > 0:
                    dropout_rate = labels.mean()
                    # If majority of labels = 1, then dropout
                    # But also consider activity: high activity may outweigh
                    if dropout_rate >= 0.7:
                        dropout = 1
                    elif dropout_rate <= 0.3:
                        dropout = 0
                    else:
                        # Borderline case: use activity as the deciding factor
                        if total_events >= 15 and duration_ms >= 60000:
                            dropout = 0  # High activity outweighs
                        else:
                            dropout = 1
                else:
                    # No labels - use heuristic
                    dropout = 1 if (total_events < 5 or duration_ms < 5000) else 0
            else:
                # Heuristic based on activity and behavior
                # High activity = low dropout
                high_activity = (total_events >= 15) and (duration_ms >= 60000) and (watch_percent >= 0.5)
                # Low activity = high dropout
                low_activity = (total_events < 5) or (duration_ms < 3000) or (watch_percent < 0.2)

                if high_activity:
                    dropout = 0
                elif low_activity:
                    dropout = 1
                else:
                    # Medium activity: dropout probability depends on factor combination
                    # Lower watchPercent and fewer events = higher dropout probability
                    dropout_score = (
                        (1.0 - watch_percent) * 0.4 +  # Low watch increases risk
                        (1.0 - min(1.0, total_events / 20.0)) * 0.3 +  # Few events
                        (1.0 - min(1.0, duration_ms / 120000.0)) * 0.3  # Short session
                    )
                    dropout = 1 if dropout_score > 0.5 else 0

            # Normalize IDs for compatibility
            course_id_hash = hash(str(course_id)) % 100
            last_object = session_group['object'].iloc[-1]
            module_id_hash = hash(str(last_object)) % 1000

            aggregated.append({
                'courseId': course_id_hash,
                'moduleId': module_id_hash,
                'durationMs': duration_ms,
                'watchPercent': watch_percent,
                'step': step,
                'dropout': dropout
            })

    if not aggregated:
        print("Error: failed to aggregate data")
        return None

    result_df = pd.DataFrame(aggregated)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_df.to_csv(output_file, index=False)

    print()
    print("=" * 60)
    print("Preparation complete!")
    print("=" * 60)
    print(f"  Total records: {len(result_df)}")
    print(f"  Dropout rate: {result_df['dropout'].mean():.2%}")
    print(f"  Average watchPercent: {result_df['watchPercent'].mean():.2%}")
    print(f"  Average duration: {result_df['durationMs'].mean()/1000:.1f} sec")
    print(f"  Saved to: {output_file}")
    print()

    return result_df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Prepare data from KDD Cup 2015 dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "input_file",
        help="Path to act-mooc.txt file or datasets/act-mooc/ directory (SNAP format)"
    )
    parser.add_argument(
        "output_file",
        help="Path to output CSV file"
    )
    parser.add_argument(
        "--max-enrollments",
        type=int,
        default=None,
        help="Maximum number of enrollments to process (for testing)"
    )

    args = parser.parse_args()

    prepare_kdd_dataset(
        args.input_file,
        args.output_file,
        max_enrollments=args.max_enrollments
    )
