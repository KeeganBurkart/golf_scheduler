# -*- coding: utf-8 -*-
"""
Streamlit Web App for Golf Group Scheduling with Player Management.
"""

import streamlit as st
import pandas as pd
import random
import io
from pathlib import Path

# ==============================================================================
# Configuration
# ==============================================================================
GROUP_SIZE = 4
# NOTE: Very high attempts might make the web app slow/timeout on free hosting.
MAX_ATTEMPTS_PER_WEEK = 3000

# ==============================================================================
# Core Scheduling Logic (Must be defined BEFORE UI calls them)
# ==============================================================================

def check_pair_uniqueness(group, past_pairs):
    """Return True if every 2-player combination in group is new."""
    for a, b in itertools.combinations(group, 2):
        if frozenset((a, b)) in past_pairs:
            return False
    return True

def generate_weekly_groups(available_golfers_names, past_pairs, num_groups_per_week, group_size):
    """Tries to generate unique groups for the week using randomization."""
    attempts = 0
    num_golfers = len(available_golfers_names)

    while attempts < MAX_ATTEMPTS_PER_WEEK:
        attempts += 1
        remaining = list(available_golfers_names)
        random.shuffle(remaining)

        week_groups = []
        formed_groups = 0
        idx = 0
        tmp_pairs = past_pairs.copy()

        while formed_groups < num_groups_per_week and idx + group_size <= num_golfers:
            candidate = remaining[idx: idx + group_size]

            if check_pair_uniqueness(candidate, tmp_pairs):
                week_groups.append(tuple(sorted(candidate)))
                formed_groups += 1
                for a, b in itertools.combinations(candidate, 2):
                    tmp_pairs.add(frozenset((a, b)))

            idx += group_size

        if formed_groups == num_groups_per_week:
            past_pairs.update(tmp_pairs)
            return week_groups

    return None

def create_schedule(golfer_list, num_weeks, group_size):
    if not golfer_list:
        return None, "Error: Golfer list is empty."

    num_golfers = len(golfer_list)
    if num_golfers % group_size != 0:
        return None, f"Error: Number of included players ({num_golfers}) must be divisible by group size ({group_size})."
    num_groups_per_week = num_golfers // group_size

    past_pairs = set()
    weekly_schedule = []

    for week_num in range(1, num_weeks + 1):
        new_week_groups = generate_weekly_groups(
            golfer_list,
            past_pairs,
            num_groups_per_week,
            group_size
        )

        if new_week_groups is None:
            failure_msg = (
                f"Error: Could not generate a valid unique grouping for Week {week_num} "
                f"after {MAX_ATTEMPTS_PER_WEEK} attempts.\n\n"
                f"This can happen if the constraints are too strict or due to the randomized nature of the search.\n\n"
                f"Suggestions:\n"
                f"- Try generating again.\n"
                f"- Reduce the number of weeks.\n"
                f"- Check if the input golfer list is correct."
            )
            return weekly_schedule, failure_msg

        weekly_schedule.append(new_week_groups)

    return weekly_schedule, f"Successfully generated schedule for all {num_weeks} weeks!"

# ==============================================================================
# Streamlit Specific Helper Functions (Defined before UI calls them)
# ==============================================================================

def initialize_state():
    """Initializes lists in session state if they don't exist."""
    if 'included_players' not in st.session_state:
        st.session_state.included_players = []
    if 'excluded_players' not in st.session_state:
        st.session_state.excluded_players = []
    if 'generated_schedule' not in st.session_state:
        st.session_state.generated_schedule = None
    if 'last_schedule_message' not in st.session_state:
        st.session_state.last_schedule_message = ""
    # Use a different key for the text input widget itself if needed,
    # but managing its value can be done directly or via on_change/callbacks.
    # Let's rely on button click reading the widget's current value for simplicity here.

def load_players_from_upload(uploaded_file_obj):
    """Loads golfer names and sets them as the initial 'included' list."""
    if uploaded_file_obj is None:
        return False # Indicate failure

    try:
        df = pd.read_excel(uploaded_file_obj, header=None, usecols=[0], engine='openpyxl')
        # Use dropna() before converting to string to handle empty rows, then get unique
        golfer_names = df[0].dropna().astype(str).unique().tolist()

        # Reset lists and store loaded names
        st.session_state.included_players = sorted(golfer_names) # Store sorted
        st.session_state.excluded_players = []
        st.session_state.generated_schedule = None # Clear previous schedule
        st.session_state.last_schedule_message = ""
        st.success(f"Successfully loaded {len(golfer_names)} unique golfers from file.")
        return True # Indicate success

    except ValueError as ve:
         st.error(f"ERROR reading Excel file structure: Ensure names are only in the first column (A). Details: {ve}")
         return False
    except Exception as e:
        st.error(f"ERROR processing Excel file: {e}")
        return False

def move_player(player_name, source_list_key, dest_list_key):
    """Moves a player between the included and excluded lists in session state."""
    # Check if the source list exists and the player is in it
    if source_list_key in st.session_state and player_name in st.session_state[source_list_key]:
        st.session_state[source_list_key].remove(player_name)
        # Ensure destination list exists and add player if not already present
        if dest_list_key not in st.session_state:
            st.session_state[dest_list_key] = [] # Initialize if missing
        if player_name not in st.session_state[dest_list_key]:
            st.session_state[dest_list_key].append(player_name)
            st.session_state[dest_list_key].sort() # Keep lists sorted
        # Clear schedule results as the player list has changed
        st.session_state.generated_schedule = None
        st.session_state.last_schedule_message = ""
    else:
        # Optional: Log or show a warning if the move couldn't happen
        print(f"Warning: Could not move '{player_name}'. Not found in '{source_list_key}'.")


# No on_change needed if we read value on button click
# def clear_add_player_input():
#    st.session_state.new_player_name_widget = ""


def add_new_player(name_to_add):
    """Adds a player from the text input to the included list."""
    name = name_to_add.strip()
    if name: # Check if name is not empty
        # Initialize lists if they don't exist (robustness)
        if 'included_players' not in st.session_state: st.session_state.included_players = []
        if 'excluded_players' not in st.session_state: st.session_state.excluded_players = []

        # Check if name already exists in either list
        if name in st.session_state.included_players or name in st.session_state.excluded_players:
            st.warning(f"Player '{name}' already exists in the lists.")
        else:
            st.session_state.included_players.append(name)
            st.session_state.included_players.sort()
            st.success(f"Added '{name}' to Included Players.")
            # Clear schedule results as the player list has changed
            st.session_state.generated_schedule = None
            st.session_state.last_schedule_message = ""
            # No need to clear input widget state manually here if we read value on click
    else:
        st.warning("Please enter a name to add.")


def format_schedule_to_dataframe(schedule, group_size):
    """Converts the schedule list into a pandas DataFrame for display."""
    if not schedule:
        return pd.DataFrame()

    output_data = []
    for week_idx, weekly_groups in enumerate(schedule):
        week_num = week_idx + 1
        if not isinstance(weekly_groups, (list, tuple)):
            print(f"Warning: Week {week_num} data is not iterable: {weekly_groups}")
            continue

        for group_idx, group_names in enumerate(weekly_groups):
             group_num = group_idx + 1
             if not isinstance(group_names, (list, tuple)):
                 print(f"Warning: Group {group_num} in Week {week_num} is not iterable: {group_names}")
                 continue

             row = {'Week': week_num, 'Group': group_num}
             for i, player_name in enumerate(group_names):
                 row[f'Player {i+1}'] = player_name
             for i in range(len(group_names), group_size):
                  row[f'Player {i+1}'] = "" # Placeholder
             output_data.append(row)

    if not output_data:
        return pd.DataFrame()

    df_output = pd.DataFrame(output_data)
    # Determine actual max players shown in data, but ensure at least GROUP_SIZE cols exist if possible
    player_cols_found = [col for col in df_output.columns if col.startswith('Player ')]
    max_player_num = 0
    if player_cols_found:
        max_player_num = max((int(col.split(' ')[1]) for col in player_cols_found), default=0)

    num_player_cols_to_ensure = max(max_player_num, group_size)
    player_cols = [f'Player {i+1}' for i in range(num_player_cols_to_ensure)]
    column_order = ['Week', 'Group'] + player_cols

    # Add missing columns if needed before reindexing
    for col in column_order:
        if col not in df_output.columns:
            df_output[col] = ""

    df_output = df_output.reindex(columns=column_order, fill_value="")
    df_output.fillna("", inplace=True) # Ensure no NaNs remain

    return df_output


def generate_excel_download_data(schedule, group_size):
    """Generates the Excel file content as bytes for download."""
    df_output = format_schedule_to_dataframe(schedule, group_size)
    if df_output.empty:
        print("Warning: Cannot generate download data, formatted DataFrame is empty.")
        return None

    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_output.to_excel(writer, index=False, sheet_name='Schedule')
        # Using context manager handles buffer correctly.
        return buffer.getvalue()
    except Exception as e:
        st.error(f"Error creating Excel file for download: {e}")
        return None


# ==============================================================================
# Streamlit User Interface (Main App Flow - Defined LAST)
# ==============================================================================

st.set_page_config(page_title="Golf Scheduler", layout="wide")
st.title("⛳ Golf Group Scheduler")
st.write("""
    Upload a list of players, manage who to include/exclude for scheduling,
    and generate weekly groups attempting to ensure unique foursomes each week.
""")

# --- Initialize State ---
# Ensures session state keys exist on first run or rerun
initialize_state()

# --- Section 1: Load and Manage Players ---
st.header("1. Manage Players")

# File Upload
uploaded_file = st.file_uploader(
    "Upload Initial Golfer List (.xlsx)",
    type=["xlsx"],
    key="file_uploader", # Give it a key
    help="Upload an Excel file (.xlsx) with golfer names listed one per row in the first column (Column A). Replaces current 'Included' list."
)

# Process upload ONLY if a file is present in the uploader widget
if uploaded_file is not None:
     # Use a button to confirm loading to prevent reload issues
    if st.button(f"Load Players from '{uploaded_file.name}'"):
        load_success = load_players_from_upload(uploaded_file)
        if load_success:
             # Try to clear the uploader widget state after successful load.
             # This is experimental, might not always work perfectly across Streamlit versions.
             # Consider advising user that file stays listed but is processed.
             # st.session_state.file_uploader = None # This might cause issues, test carefully
             st.rerun() # Rerun to update lists display after loading


# Add New Player Input
st.subheader("Add New Player")
col_add1, col_add2 = st.columns([3,1])
with col_add1:
    # Use a unique key for the text input widget
    new_player_name_input = st.text_input(
        "New Player Name:",
        key="new_player_name_widget"
    )
with col_add2:
    st.write("") # Vertical alignment spacer
    st.write("") # Vertical alignment spacer
    # When button is clicked, call add_new_player with the CURRENT value of the text input
    if st.button("Add Player", help="Adds the name to the 'Included Players' list."):
        add_new_player(new_player_name_input)
        # Clear the widget's state after adding
        st.session_state.new_player_name_widget = ""
        st.rerun() # Rerun to reflect changes


# Display Included/Excluded Lists side-by-side
st.subheader("Player Lists")
col_inc, col_exc = st.columns(2)

with col_inc:
    included_list = st.session_state.get('included_players', [])
    st.markdown(f"**Included Players ({len(included_list)})**")
    st.caption("Click name to Exclude ->")
    if not included_list:
        st.write("_No players currently included._")
    else:
        # Create buttons dynamically
        for player in included_list:
            # Use player name in the key to make it unique
            if st.button(player, key=f"exc_{player}", help=f"Exclude {player}"):
                 move_player(player, 'included_players', 'excluded_players')
                 st.rerun() # Force rerun immediately


with col_exc:
    excluded_list = st.session_state.get('excluded_players', [])
    st.markdown(f"**Excluded Players ({len(excluded_list)})**")
    st.caption("<- Click name to Include")
    if not excluded_list:
        st.write("_No players currently excluded._")
    else:
        # Create buttons dynamically
        for player in excluded_list:
            if st.button(player, key=f"inc_{player}", help=f"Include {player}"):
                 move_player(player, 'excluded_players', 'included_players')
                 st.rerun() # Force rerun


# --- Section 2: Generate Schedule ---
st.header("2. Generate Schedule")

num_weeks_input = st.number_input(
    "Number of Weeks to Schedule",
    min_value=1,
    step=1,
    value=st.session_state.get("num_weeks_value", 12), # Try to retain value
    format="%d",
    key="num_weeks", # Use key to access value below
    help="How many weeks do you need the schedule for?"
)
# Store value in session state to attempt retaining it across reruns
st.session_state.num_weeks_value = num_weeks_input


# Validation for Generation
# Use .get() for safer access to session state
players_to_schedule = st.session_state.get('included_players', [])
num_players = len(players_to_schedule)
num_weeks = int(num_weeks_input) # Already validated as >= 1 by number_input

validation_ok = True
validation_messages = []

if num_players == 0:
    validation_messages.append("No players are included for scheduling.")
    validation_ok = False
elif num_players % GROUP_SIZE != 0:
    validation_messages.append(f"Number of included players ({num_players}) must be divisible by {GROUP_SIZE}.")
    validation_ok = False
# num_weeks validation handled by widget min_value

if validation_messages:
    for msg in validation_messages:
        st.warning(msg)

# Generation Button
if st.button("Generate Schedule", disabled=(not validation_ok)):
    st.session_state.generated_schedule = None # Clear old schedule display
    st.session_state.last_schedule_message = "" # Clear old message

    # Show spinner during the potentially long generation process
    with st.spinner(f"Generating schedule for {num_weeks} weeks... This may take time."):
        # *** Call the core logic function which is DEFINED ABOVE ***
        final_schedule, result_message = create_schedule(
            players_to_schedule, # Use only included players
            num_weeks,
            GROUP_SIZE
        )

    # Store results in session state for display after rerun
    st.session_state.generated_schedule = final_schedule
    st.session_state.last_schedule_message = result_message
    st.rerun() # Rerun to display the schedule and message below


# --- Section 3: Display and Download Schedule ---
st.header("3. Schedule Results")

# Display the message from the last generation attempt stored in session state
last_msg = st.session_state.get('last_schedule_message', "")
if last_msg:
     if "Error:" in last_msg or "Could not generate" in last_msg :
         st.error(last_msg)
         # If error occurred but we have partial schedule, mention it
         if st.session_state.get('generated_schedule'):
             st.warning("Partial schedule generated up to the point of failure.")
     else:
         st.success(last_msg)
         # Only show balloons on full success
         if st.session_state.get('generated_schedule') and len(st.session_state.generated_schedule) == num_weeks:
             st.balloons()


# Display the generated schedule (full or partial) if it exists in session state
current_schedule = st.session_state.get('generated_schedule')
if current_schedule:
    st.subheader("Generated Schedule Display")
    schedule_df = format_schedule_to_dataframe(current_schedule, GROUP_SIZE)
    if not schedule_df.empty:
        # Use st.dataframe for interactive table, height might need adjustment
        st.dataframe(schedule_df, hide_index=True, height=(min(len(schedule_df), 20) + 1) * 35 + 3)

        st.subheader("Download Schedule")
        excel_data = generate_excel_download_data(current_schedule, GROUP_SIZE)
        if excel_data:
            # Use actual number of players and generated weeks in filename
            actual_weeks_generated = len(current_schedule)
            num_players_in_schedule = len(st.session_state.get('included_players', []))
            st.download_button(
                label="Download Schedule as Excel (.xlsx)",
                data=excel_data,
                file_name=f"golf_schedule_{num_players_in_schedule}p_{actual_weeks_generated}w.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_button" # Add key for potential state management
            )
        else:
            st.error("Could not prepare schedule for download.")
    # Handle case where formatting might fail even if schedule list exists
    elif last_msg and "Error:" not in last_msg:
         st.warning("Schedule data exists but could not be formatted for display.")

# If no schedule exists in state, but last message wasn't an error (e.g., after clearing)
elif not current_schedule and last_msg and "Error:" not in last_msg:
     st.info("No schedule data to display.")

# Default message if nothing has happened yet
elif not last_msg:
    st.info("Generate a schedule using the button above to see results here.")


# --- Footer ---
st.markdown("---")
st.caption("Golf Scheduler App - v2.1")
