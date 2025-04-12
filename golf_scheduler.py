import streamlit as st
import pandas as pd
import random
import io
from pathlib import Path

# --- Core Scheduling Logic (mostly unchanged) ---

# Configuration
GROUP_SIZE = 4
MAX_ATTEMPTS_PER_WEEK = 3000

# (check_group_uniqueness, generate_weekly_groups, create_schedule functions
#  remain the same as in the previous web app version - assuming they are defined
#  above this point in your actual file or imported)
# Make sure create_schedule returns (schedule_list_or_None, status_message)

# --- Streamlit Specific Helper Functions ---

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
    if 'new_player_name' not in st.session_state:
        st.session_state.new_player_name = ""


def load_players_from_upload(uploaded_file_obj):
    """Loads golfer names and sets them as the initial 'included' list."""
    if uploaded_file_obj is None:
        # This shouldn't happen if called correctly, but safeguard
        return False

    try:
        # Read directly from the uploaded file object in memory
        df = pd.read_excel(uploaded_file_obj, header=None, usecols=[0], engine='openpyxl')
        golfer_names = df[0].astype(str).unique().tolist() # Get unique names as list

        # Reset lists and store loaded names
        st.session_state.included_players = sorted(golfer_names) # Store sorted
        st.session_state.excluded_players = []
        st.session_state.generated_schedule = None # Clear previous schedule
        st.session_state.last_schedule_message = ""
        st.success(f"Successfully loaded {len(golfer_names)} unique golfers from file.")
        return True

    except ValueError as ve:
         st.error(f"ERROR reading Excel file structure: Make sure names are only in the first column (A). Details: {ve}")
         return False
    except Exception as e:
        st.error(f"ERROR processing Excel file: {e}")
        return False

def move_player(player_name, source_list_key, dest_list_key):
    """Moves a player between the included and excluded lists in session state."""
    if player_name in st.session_state[source_list_key]:
        st.session_state[source_list_key].remove(player_name)
        # Add to destination only if not already there (safety check)
        if player_name not in st.session_state[dest_list_key]:
            st.session_state[dest_list_key].append(player_name)
            st.session_state[dest_list_key].sort() # Keep lists sorted
        st.session_state.generated_schedule = None # Clear schedule if lists change
        st.session_state.last_schedule_message = ""


def add_new_player():
    """Adds a player from the text input to the included list."""
    name = st.session_state.new_player_name.strip()
    if name: # Check if name is not empty
        # Check if name already exists in either list
        if name in st.session_state.included_players or name in st.session_state.excluded_players:
            st.warning(f"Player '{name}' already exists in the lists.")
        else:
            st.session_state.included_players.append(name)
            st.session_state.included_players.sort()
            st.success(f"Added '{name}' to Included Players.")
            st.session_state.new_player_name = "" # Clear input field state
            st.session_state.generated_schedule = None # Clear schedule
            st.session_state.last_schedule_message = ""

    else:
        st.warning("Please enter a name to add.")


def format_schedule_to_dataframe(schedule, group_size):
    """Converts the schedule list into a pandas DataFrame for display."""
    if not schedule:
        return pd.DataFrame() # Return empty DataFrame if no schedule

    output_data = []
    for week_idx, weekly_groups in enumerate(schedule):
        week_num = week_idx + 1
        # Ensure weekly_groups is iterable (list of tuples)
        if not isinstance(weekly_groups, (list, tuple)):
            st.warning(f"Week {week_num} data is not in the expected format. Skipping display.")
            continue

        max_group_len = 0
        formatted_groups = []
        for group_idx, group_names in enumerate(weekly_groups):
             # Ensure group_names is iterable (tuple of names)
             if not isinstance(group_names, (list, tuple)):
                 st.warning(f"Group {group_idx+1} in Week {week_num} is not in the expected format. Skipping.")
                 continue

             group_num = group_idx + 1
             row = {'Week': week_num, 'Group': group_num}
             for i, player_name in enumerate(group_names):
                 row[f'Player {i+1}'] = player_name
             # Add placeholders if a group is smaller than group_size (shouldn't happen with current logic)
             for i in range(len(group_names), group_size):
                  row[f'Player {i+1}'] = ""
             formatted_groups.append(row)
             max_group_len = max(max_group_len, len(group_names)) # Track max actual players in groups this week

        output_data.extend(formatted_groups)

    if not output_data:
        return pd.DataFrame()

    df_output = pd.DataFrame(output_data)

    # Determine player columns dynamically based on data, up to GROUP_SIZE
    actual_max_players = max((int(col.split(' ')[1]) for col in df_output.columns if col.startswith('Player ')), default=0)
    num_player_cols_to_show = min(max(actual_max_players, group_size), group_size) # Show at least group_size cols if possible

    player_cols = [f'Player {i+1}' for i in range(num_player_cols_to_show)]
    column_order = ['Week', 'Group'] + player_cols

    # Ensure necessary columns exist before reordering
    for col in column_order:
        if col not in df_output.columns:
            df_output[col] = "" # Add missing columns as empty

    # Reindex might fill NaNs, ensure we fill with ""
    df_output = df_output.reindex(columns=column_order, fill_value="")
    df_output.fillna("", inplace=True) # Replace any remaining NaNs

    return df_output


def generate_excel_download_data(schedule, group_size):
    """Generates the Excel file content as bytes for download. (Uses the formatting function)"""
    df_output = format_schedule_to_dataframe(schedule, group_size)
    if df_output.empty:
        st.error("Cannot generate download: No schedule data formatted.")
        return None

    buffer = io.BytesIO()
    # Use ExcelWriter to explicitly handle the buffer
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_output.to_excel(writer, index=False, sheet_name='Schedule')
    # No need to seek(0) when using context manager for ExcelWriter

    return buffer.getvalue()


# --- Streamlit App UI ---

st.set_page_config(page_title="Golf Scheduler", layout="wide") # Use wide layout for side-by-side lists
st.title("⛳ Golf Group Scheduler")
st.write("""
    Upload a list of players, manage who to include/exclude for scheduling,
    and generate weekly groups attempting to ensure unique foursomes each week.
""")

# --- Initialize State ---
initialize_state()

# --- Section 1: Load and Manage Players ---
st.header("1. Manage Players")

# File Upload
uploaded_file = st.file_uploader(
    "Upload Initial Golfer List (.xlsx)",
    type=["xlsx"],
    help="Upload an Excel file (.xlsx) with golfer names listed one per row in the first column (Column A). This will replace the current 'Included' list."
)

# Process upload if a new file is provided
if uploaded_file is not None:
    # Use a button to confirm loading, preventing reload on every interaction
    if st.button(f"Load Players from '{uploaded_file.name}'"):
        load_players_from_upload(uploaded_file)
        # Clear the file uploader state after processing to prevent reload loop
        # This is a bit tricky, might require more advanced state management or
        # relying on the user not interacting further until load is done.
        # For now, we proceed, but beware of potential reruns.


# Add New Player Input
st.subheader("Add New Player")
col_add1, col_add2 = st.columns([3,1])
with col_add1:
    st.text_input(
        "New Player Name:",
        key="new_player_name", # Bind to session state key
        on_change=None # Action happens on button click
    )
with col_add2:
    # Need this vertical space alignment hack
    st.write("")
    st.write("")
    st.button("Add Player", on_click=add_new_player, help="Adds the name to the 'Included Players' list.")


# Display Included/Excluded Lists side-by-side
st.subheader("Player Lists")
col_inc, col_exc = st.columns(2)

with col_inc:
    st.markdown(f"**Included Players ({len(st.session_state.included_players)})**")
    st.caption("Click name to Exclude ->")
    if not st.session_state.included_players:
        st.write("_No players currently included._")
    else:
        # Display players with buttons to move them
        # Use containers for better layout if needed, but simple buttons work
        for player in st.session_state.included_players:
            if st.button(player, key=f"exc_{player}", help=f"Exclude {player}"):
                 move_player(player, 'included_players', 'excluded_players')
                 st.rerun() # Force rerun immediately after state change for UI update


with col_exc:
    st.markdown(f"**Excluded Players ({len(st.session_state.excluded_players)})**")
    st.caption("<- Click name to Include")
    if not st.session_state.excluded_players:
        st.write("_No players currently excluded._")
    else:
        for player in st.session_state.excluded_players:
             if st.button(player, key=f"inc_{player}", help=f"Include {player}"):
                 move_player(player, 'excluded_players', 'included_players')
                 st.rerun() # Force rerun


# --- Section 2: Generate Schedule ---
st.header("2. Generate Schedule")

num_weeks_input = st.number_input(
    "Number of Weeks to Schedule",
    min_value=1,
    step=1,
    value=12, # Default value
    format="%d",
    key="num_weeks",
    help="How many weeks do you need the schedule for?"
)

# Validation for Generation
players_to_schedule = st.session_state.included_players
num_players = len(players_to_schedule)
validation_ok = True
validation_messages = []

if num_players == 0:
    validation_messages.append("No players are included for scheduling.")
    validation_ok = False
elif num_players % GROUP_SIZE != 0:
    validation_messages.append(f"Number of included players ({num_players}) must be divisible by {GROUP_SIZE}.")
    validation_ok = False
if int(num_weeks_input) <= 0:
     validation_messages.append("Number of weeks must be positive.")
     validation_ok = False

if validation_messages:
    for msg in validation_messages:
        st.warning(msg)

# Generation Button
if st.button("Generate Schedule", disabled=(not validation_ok)):
    st.session_state.generated_schedule = None # Clear old schedule display
    st.session_state.last_schedule_message = "" # Clear old message

    with st.spinner(f"Generating schedule for {num_weeks_input} weeks... This may take time."):
        # Call the core logic function with ONLY included players
        final_schedule, result_message = create_schedule(
            players_to_schedule,
            int(num_weeks_input),
            GROUP_SIZE
        )

    # Store results in session state for display after rerun
    st.session_state.generated_schedule = final_schedule
    st.session_state.last_schedule_message = result_message
    st.rerun() # Rerun to display the schedule and message below


# --- Section 3: Display and Download Schedule ---
st.header("3. Schedule Results")

# Display the message from the last generation attempt
if st.session_state.last_schedule_message:
     if "Error:" in st.session_state.last_schedule_message or "Could not generate" in st.session_state.last_schedule_message :
         st.error(st.session_state.last_schedule_message)
     else:
         st.success(st.session_state.last_schedule_message)
         st.balloons()


# Display the generated schedule if it exists
if st.session_state.generated_schedule:
    st.subheader("Generated Schedule Display")
    schedule_df = format_schedule_to_dataframe(st.session_state.generated_schedule, GROUP_SIZE)
    if not schedule_df.empty:
        st.dataframe(schedule_df, hide_index=True) # Display schedule in a table

        st.subheader("Download Schedule")
        excel_data = generate_excel_download_data(st.session_state.generated_schedule, GROUP_SIZE)
        if excel_data:
            st.download_button(
                label="Download Schedule as Excel (.xlsx)",
                data=excel_data,
                file_name=f"golf_schedule_{len(st.session_state.included_players)}p_{len(st.session_state.generated_schedule)}w.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Could not prepare schedule for download.")
    else:
        st.info("Schedule generated, but no data available for display (this might indicate an issue).")

elif st.session_state.last_schedule_message and "Error:" not in st.session_state.last_schedule_message:
     st.info("Schedule generation completed, but no schedule data is currently stored.") # Should not happen if successful

else:
    st.info("Generate a schedule using the button above to see results here.")


# --- Footer ---
st.markdown("---")
st.caption("Scheduler v2 - Manage player inclusion and view schedule.")
