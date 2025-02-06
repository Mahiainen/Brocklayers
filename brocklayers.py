# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

import re
import sys
import logging
import os
import argparse

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Configure logging to save in the script's directory
log_file_path = os.path.join(script_dir, "z_shift_log.txt")
logging.basicConfig(
    filename=log_file_path,
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

MIN_LAYER_HEIGHT = 0.15  # Thinner layer
MAX_LAYER_HEIGHT = 0.3   # Thicker layer
MIN_LINE_WIDTH = 0.4     # Narrower extrusion
MAX_LINE_WIDTH = 0.5     # Wider extrusion

def calculate_layer_settings(layer_number, total_layers):
    if layer_number % 2 == 0:
        return {
            'layer_height': MAX_LAYER_HEIGHT,
            'line_width': MIN_LINE_WIDTH
        }
    else:
        return {
            'layer_height': MIN_LAYER_HEIGHT,
            'line_width': MAX_LINE_WIDTH
        }

def process_gcode(input_file, layer_height, extrusion_multiplier):
    current_layer = 0
    current_z = 0.0
    perimeter_type = None
    perimeter_block_count = 0
    inside_perimeter_block = False
    z_shift = layer_height * 0.5
    logging.info("Starting G-code processing")
    logging.info(f"Input file: {input_file}")

    # Read the input G-code
    with open(input_file, 'r') as infile:
        lines = infile.readlines()

    # Identify the total number of layers by looking for `G1 Z` commands
    total_layers = sum(1 for line in lines if line.startswith("G1 Z"))

    # Process the G-code
    modified_lines = []
    for line in lines:
        # Detect layer changes
        if line.startswith("G1 Z"):
            z_match = re.search(r'Z([-\d.]+)', line)
            if z_match:
                current_z = float(z_match.group(1))
                current_layer = int(current_z / layer_height)

                perimeter_block_count = 0  # Reset block counter for new layer
                logging.info(f"Layer {current_layer} detected at Z={current_z:.3f}")
            modified_lines.append(line)
            continue

        # Detect perimeter types from PrusaSlicer comments
        if ";TYPE:External perimeter" in line or ";TYPE:Outer wall" in line:
            perimeter_type = "external"
            inside_perimeter_block = False
            logging.info(f"External perimeter detected at layer {current_layer}")
        elif ";TYPE:Perimeter" in line or ";TYPE:Inner wall" in line:
            perimeter_type = "internal"
            inside_perimeter_block = False
            logging.info(f"Internal perimeter block started at layer {current_layer}")
        elif ";TYPE:" in line:  # Reset for other types
            perimeter_type = None
            inside_perimeter_block = False

        # Group lines into perimeter blocks
        if perimeter_type == "internal" and line.startswith("G1") and "X" in line and "Y" in line and "E" in line:
            # Start a new perimeter block if not already inside one
            if not inside_perimeter_block:
                perimeter_block_count += 1
                inside_perimeter_block = True
                logging.info(f"Perimeter block #{perimeter_block_count} detected at layer {current_layer}")

                # Calculate current layer settings
                layer_settings = calculate_layer_settings(current_layer, total_layers)
                logging.info(f"Using layer settings: {layer_settings}")

                # Insert the corresponding Z height for this block
                if perimeter_block_count % 2 == 1:  # Apply Z-shift to odd-numbered blocks
                    adjusted_z = current_z + z_shift * layer_settings['layer_height']
                    logging.info(f"Inserting G1 Z{adjusted_z:.3f} for shifted perimeter block #{perimeter_block_count}")
                    modified_lines.append(f"G1 Z{adjusted_z:.3f} ; Shifted Z for block #{perimeter_block_count}\n")
                else:  # Reset to the true layer height for even-numbered blocks
                    logging.info(f"Inserting G1 Z{current_z:.3f} for non-shifted perimeter block #{perimeter_block_count}")
                    modified_lines.append(f"G1 Z{current_z:.3f} ; Reset Z for block #{perimeter_block_count}\n")

                # Adjust extrusion (`E` values) based on current layer settings
                e_match = re.search(r'E([-\d.]+)', line)
                if e_match:
                    e_value = float(e_match.group(1))
                    new_e_value = e_value * (layer_settings['line_width'] / 0.4)  # Assuming default line width is 0.4
                    logging.info(f"Adjusting E value from {e_value:.5f} to {new_e_value:.5f}")
                    line = re.sub(r'E[-\d.]+', f'E{new_e_value:.5f}', line).strip()
                    line += f" ; Adjusted E for layer settings, block #{perimeter_block_count}\n"

            # End of perimeter block
            inside_perimeter_block = False

        modified_lines.append(line)

    # Overwrite the input file with the modified G-code
    with open(input_file, 'w') as outfile:
        outfile.writelines(modified_lines)

    logging.info("G-code processing completed")
    logging.info(f"Log file saved at {log_file_path}")

# Main execution
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post-process G-code for Z-shifting and extrusion adjustments.")
    parser.add_argument("input_file", help="Path to the input G-code file")
    parser.add_argument("-layerHeight", type=float, default=0.2, help="Layer height in mm (default: 0.2mm)")
    parser.add_argument("-extrusionMultiplier", type=float, default=1, help="Extrusion multiplier for first layer (default: 1.5x)")
    args = parser.parse_args()

    process_gcode(
        input_file=args.input_file,
        layer_height=args.layerHeight,
        extrusion_multiplier=args.extrusionMultiplier,
    )
