import streamlit as st
import pandas as pd
import random
import io         # Needed for handling file download in memory
from pathlib import Path

# --- Core Scheduling Logic (mostly unchanged) ---

# Configuration
GROUP_SIZE = 4
# NOTE: Very high attempts might make the web app slow/timeout on free hosting.
# Consider lowering if generation takes too long.
MAX_ATTEMPTS_PER_WEEK = 3000 # Reduced slightly for web context

def check_group_uniqueness(group, past_groups_by_player):
    """Checks if this exact group (frozenset) is new for ALL members."""
    for player in group:
        if player in past_groups_by_player and group in past_groups_by_player[player]:
            return False
    return True

def generate_weekly_groups(available_golfers_names, past_groups_by_player, num_groups_per_week, group_size):
    """Tries to generate unique groups for the week using randomization."""
    attempts = 0
    num_golfers = len(available_golfers_names)

    while attempts < MAX_ATTEMPTS_PER_WEEK:
        attempts += 1
        remaining_golfers = list(available_golfers_names)
        random.shuffle(remaining_golfers)
        current_week_groups = []
        possible = True

        if num_golfers < group_size :
             # Should be caught by earlier validation, but good failsafe
             raise ValueError("Not enough golfers to form a group.")

        index = 0
        while len(current_week_groups) < num_groups_per_week and index + group_size <= len(remaining_golfers):
            potential_group_list = remaining_golfers[index : index + group_size]
            potential_group_fset = frozenset(potential_group_list)

            if check_group_uniqueness(potential_group_fset, past_groups_by_player):
                current_week_groups.append(tuple(sorted(potential_group_list)))
                index += group_size
            else:
                possible = False
                break

        if possible and len(current_week_groups) == num_groups_per_week:
             return current_week_groups

    # Failed after max attempts
    return None # Signifies failure for this week

def create_schedule(golfer_list, num_weeks, group_size):
    """
    Main function to generate the schedule.
    Returns tuple: (schedule_list_or_None, status_message)
    """
    if not golfer_list:
        return None, "Error: Golfer list is empty."

    num_golfers = len(golfer_list)
    if num_golfers % group_size != 0:
         return None, f"Error: Number of golfers ({num_golfers}) is not divisible by group size ({group_size})."
    num_groups_per_week = num_golfers // group_size

    past_groups_by_player = {player: set() for player in golfer_list}
    weekly_schedule = []

    st.info(f"Attempting generation for {num_weeks} weeks ({num_groups_per_week} groups/week)...")

    for week_num in range(1, num_weeks + 1):
        # Provide progress update within the loop if desired, though spinner is often enough
        # st.write(f"Generating Week {week_num}/{num_weeks}...") # Can be verbose

        new_week_groups = generate_weekly_groups(
            golfer_list,
            past_groups_by_player,
            num_groups_per_week,
            group_size
        )

        if new_week_groups is None:
            failure_msg = (
                f"Error: Could not generate a valid unique grouping for Week {week_num} "
                f"after {MAX_ATTEMPTS_PER_WEEK} attempts.\n\n"
                f"This can happen if the constraints are too strict (especially for many weeks) "
                f"or due to the randomized nature of the search.\n\n"
                f"Suggestions:\n"
                f"- Try generating again (might find a solution next time).\n"
                f"- Reduce the number of weeks.\n"
                f"- Check if the input golfer list is correct."
            )
            # Return partial schedule found so far and the error message
            return weekly_schedule, failure_msg

        weekly_schedule.append(new_week_groups)

        # Update history
        for group_tuple in new_week_groups:
            group_fset = frozenset(group_tuple)
            for player in group_fset:
                 if player in past_groups_by_player:
                    past_groups_by_player[player].add(group_fset)

    # If loop completes, generation was successful
    success_msg = f"Successfully generated schedule for all {num_weeks} weeks!"
    return weekly_schedule, success_msg


# --- Streamlit Specific Helper Functions ---

def load_golfers_from_upload(uploaded_file_obj, expected_num_golfers):
    """Loads golfer names from the first column of an uploaded Excel file object."""
    if uploaded_file_obj is None:
        st.error("ERROR: No file uploaded!")
        return None
    try:
        # Read directly from the uploaded file object in memory
        df = pd.read_excel(uploaded_file_obj, header=None, usecols=[0], engine='openpyxl')
        golfer_names = df[0].astype(str).tolist()

        # Basic validations
        if len(set(golfer_names)) != len(golfer_names):
             st.error("ERROR: Duplicate names found in the uploaded file. Please ensure all names are unique.")
             return None
        if len(golfer_names) != expected_num_golfers:
            st.error(f"ERROR: Expected {expected_num_golfers} golfers based on input, but found {len(golfer_names)} in the file.")
            return None

        st.success(f"Successfully loaded {len(golfer_names)} golfers.")
        return golfer_names

    except ValueError as ve:
         st.error(f"ERROR reading Excel file structure: Make sure names are only in the first column (A). Details: {ve}")
         return None
    except Exception as e:
        st.error(f"ERROR processing Excel file: {e}")
        return None


def generate_excel_download_data(schedule, group_size):
    """Generates the Excel file content as bytes for download."""
    if not schedule:
        st.error("Cannot generate download: No schedule data available.")
        return None

    output_data = []
    for week_idx, weekly_groups in enumerate(schedule):
        week_num = week_idx + 1
        for group_idx, group_names in enumerate(weekly_groups):
            group_num = group_idx + 1
            row = {'Week': week_num, 'Group': group_num}
            for i, player_name in enumerate(group_names):
                row[f'Player {i+1}'] = player_name
            # Add placeholders if a group is smaller than expected (shouldn't happen)
            for i in range(len(group_names), group_size):
                 row[f'Player {i+1}'] = ""
            output_data.append(row)

    df_output = pd.DataFrame(output_data)
    player_cols = [f'Player {i+1}' for i in range(group_size)]
    column_order = ['Week', 'Group'] + player_cols
    df_output = df_output.reindex(columns=column_order, fill_value="")

    # Save to an in-memory buffer
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_output.to_excel(writer, index=False, sheet_name='Schedule')
    # The buffer is ready, no need to buffer.seek(0) with ExcelWriter context manager

    return buffer.getvalue() # Return the bytes


# --- Streamlit User Interface ---

st.set_page_config(page_title="Golf Scheduler", layout="centered")
st.title("⛳ Golf Group Scheduler")
st.write("This tool attempts to create weekly golf groups ensuring each player has a unique group composition each week.")

# --- Inputs ---
st.header("1. Setup")

uploaded_file = st.file_uploader(
    "Upload Golfer List (.xlsx)",
    type=["xlsx"],
    help="Upload an Excel file (.xlsx) with golfer names listed one per row in the first column (Column A)."
)

col1, col2 = st.columns(2)
with col1:
    num_players_input = st.number_input(
        "Total Number of Players",
        min_value=GROUP_SIZE, # Minimum players must form at least one group
        step=1,
        format="%d",
        help=f"Enter the total number of golfers listed in your file. Must be divisible by {GROUP_SIZE}."
    )
with col2:
    num_weeks_input = st.number_input(
        "Number of Weeks to Schedule",
        min_value=1,
        step=1,
        format="%d",
        help="How many weeks do you need the schedule for?"
    )

# --- Validation & Generation Trigger ---
st.header("2. Generate")

# Derived values and validation messages
num_players = int(num_players_input) if num_players_input else 0
num_weeks = int(num_weeks_input) if num_weeks_input else 0
validation_ok = True
if num_players <= 0:
    st.warning("Please enter the total number of players.")
    validation_ok = False
elif num_players % GROUP_SIZE != 0:
    st.error(f"Number of players ({num_players}) must be divisible by the group size ({GROUP_SIZE}).")
    validation_ok = False

if num_weeks <= 0:
    st.warning("Please enter the number of weeks.")
    validation_ok = False

if uploaded_file is None:
    st.warning("Please upload the golfer list file.")
    validation_ok = False


# Only enable the button if validation passes
if st.button("Generate Schedule", disabled=(not validation_ok)):
    st.info("Loading golfer names...")
    golfers = load_golfers_from_upload(uploaded_file, num_players)

    if golfers:
        # Show spinner during the potentially long generation process
        with st.spinner(f"Generating schedule for {num_weeks} weeks... This may take a moment."):
            # Call the core logic function
            final_schedule, result_message = create_schedule(golfers, num_weeks, GROUP_SIZE)

        # Display result message (success or failure)
        if "Error:" in result_message:
            st.error(result_message)
            if final_schedule: # If partial schedule exists on error
                 st.warning("Partial schedule generated up to the point of failure.")
        else:
            st.success(result_message)
            st.balloons()

        # Provide download button if any schedule (even partial) was generated
        if final_schedule:
            st.header("3. Download")
            excel_data = generate_excel_download_data(final_schedule, GROUP_SIZE)
            if excel_data:
                st.download_button(
                    label="Download Schedule as Excel (.xlsx)",
                    data=excel_data,
                    file_name=f"golf_schedule_{num_players}p_{len(final_schedule)}w.xlsx", # Use actual weeks generated
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                 st.error("Could not prepare schedule for download.")

# --- Footer ---
st.markdown("---")
st.caption("Scheduler based on randomized group assignment with uniqueness constraint.")