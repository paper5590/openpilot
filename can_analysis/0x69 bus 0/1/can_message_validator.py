#!/usr/bin/env python3
"""
CAN Message Validator for Address 0x69
Validates counters and checksums based on analysis of 48,090 messages
"""

import csv

class CANMessageValidator:
    def __init__(self, training_file=None):
        """
        Initialize validator, optionally building checksum lookup from training data
        
        Args:
            training_file: Path to CSV file with known-good messages (optional)
        """
        self.checksum_lookup = {}
        self.b1_counter = None  # 4-bit counter, increments by 2
        self.b5_counter = None  # 4-bit counter, increments by 4
        
        if training_file:
            self.build_lookup_table(training_file)
    
    def build_lookup_table(self, csv_file):
        """Build checksum lookup table from known-good messages"""
        with open(csv_file, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                data_hex = row[3].replace('0x', '')
                data_bytes = [int(data_hex[i:i+2], 16) for i in range(0, 16, 2)]
                
                b1, b2, b5, b6 = data_bytes[1], data_bytes[2], data_bytes[5], data_bytes[6]
                key = (b1, b2, b5)
                
                if key in self.checksum_lookup and self.checksum_lookup[key] != b6:
                    print(f"WARNING: Inconsistent checksum for {key}")
                
                self.checksum_lookup[key] = b6
        
        print(f"Loaded {len(self.checksum_lookup)} checksum entries")
    
    def get_checksum(self, b1, b2, b5):
        """
        Get expected checksum for given byte values
        
        Args:
            b1, b2, b5: Byte values
            
        Returns:
            Expected checksum byte, or None if unknown
        """
        return self.checksum_lookup.get((b1, b2, b5))
    
    def validate_counter_b1(self, b1_low_nibble):
        """
        Validate Byte 1 low nibble counter (increments by 2 mod 16)
        
        Args:
            b1_low_nibble: Current low nibble value (0-15)
            
        Returns:
            tuple: (is_valid, message)
        """
        if self.b1_counter is None:
            # First message, initialize
            self.b1_counter = b1_low_nibble
            return (True, "Counter initialized")
        
        expected = (self.b1_counter + 2) % 16
        
        if b1_low_nibble == expected:
            self.b1_counter = b1_low_nibble
            return (True, "Counter valid")
        else:
            # Check how many messages were skipped
            diff = (b1_low_nibble - self.b1_counter) % 16
            if diff % 2 == 0:
                skipped = (diff // 2) - 1
                self.b1_counter = b1_low_nibble
                return (False, f"Counter skip detected: {skipped} message(s) lost")
            else:
                return (False, f"Counter error: expected {expected:X}, got {b1_low_nibble:X}")
    
    def validate_counter_b5(self, b5_low_nibble):
        """
        Validate Byte 5 low nibble counter (increments by 4 mod 16)
        
        Args:
            b5_low_nibble: Current low nibble value (0-15)
            
        Returns:
            tuple: (is_valid, message)
        """
        if self.b5_counter is None:
            # First message, initialize
            self.b5_counter = b5_low_nibble
            return (True, "Counter initialized")
        
        expected = (self.b5_counter + 4) % 16
        
        if b5_low_nibble == expected:
            self.b5_counter = b5_low_nibble
            return (True, "Counter valid")
        else:
            # Check how many messages were skipped
            diff = (b5_low_nibble - self.b5_counter) % 16
            if diff % 4 == 0:
                skipped = (diff // 4) - 1
                self.b5_counter = b5_low_nibble
                return (False, f"Counter skip detected: {skipped} message(s) lost")
            else:
                return (False, f"Counter error: expected {expected:X}, got {b5_low_nibble:X}")
    
    def validate_message(self, data_bytes, verbose=True):
        """
        Validate a complete CAN message
        
        Args:
            data_bytes: List of 8 bytes
            verbose: Print detailed validation results
            
        Returns:
            dict: Validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Extract fields
        b0, b1, b2, b3, b4, b5, b6, b7 = data_bytes
        b1_low = b1 & 0x0F
        b5_low = b5 & 0x0F
        
        # Validate constant bytes
        if b0 != 0x18:
            results['valid'] = False
            results['errors'].append(f"Byte 0 should be 0x18, got 0x{b0:02X}")
        
        if b3 != 0x00:
            results['warnings'].append(f"Byte 3 unusual: 0x{b3:02X} (expected 0x00)")
        
        if b4 != 0x00:
            results['warnings'].append(f"Byte 4 unusual: 0x{b4:02X} (expected 0x00)")
        
        if b7 != 0x00:
            results['warnings'].append(f"Byte 7 unusual: 0x{b7:02X} (expected 0x00)")
        
        # Validate counters
        valid_b1, msg_b1 = self.validate_counter_b1(b1_low)
        if not valid_b1:
            results['valid'] = False
            results['errors'].append(f"Byte 1 counter: {msg_b1}")
        elif verbose and "skip" in msg_b1:
            results['warnings'].append(f"Byte 1 counter: {msg_b1}")
        
        valid_b5, msg_b5 = self.validate_counter_b5(b5_low)
        if not valid_b5:
            results['valid'] = False
            results['errors'].append(f"Byte 5 counter: {msg_b5}")
        elif verbose and "skip" in msg_b5:
            results['warnings'].append(f"Byte 5 counter: {msg_b5}")
        
        # Validate checksum
        expected_checksum = self.get_checksum(b1, b2, b5)
        if expected_checksum is not None:
            if b6 != expected_checksum:
                results['valid'] = False
                results['errors'].append(
                    f"Checksum invalid: expected 0x{expected_checksum:02X}, got 0x{b6:02X}")
        else:
            results['warnings'].append(
                f"Unknown checksum combination (0x{b1:02X}, 0x{b2:02X}, 0x{b5:02X})")
        
        return results
    
    def reset_counters(self):
        """Reset counter tracking (for new message stream)"""
        self.b1_counter = None
        self.b5_counter = None


# Example usage
if __name__ == "__main__":
    import sys
    
    # Initialize validator with training data
    if len(sys.argv) > 1:
        training_file = sys.argv[1]
        print(f"Loading training data from {training_file}...")
        validator = CANMessageValidator(training_file)
    else:
        print("Usage: python validator.py <training_csv_file> [test_csv_file]")
        print("\nExample: python validator.py known_good_messages.csv test_messages.csv")
        sys.exit(1)
    
    # Test on messages
    if len(sys.argv) > 2:
        test_file = sys.argv[2]
        print(f"\nValidating messages from {test_file}...")
        
        with open(test_file, 'r') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                data_hex = row[3].replace('0x', '')
                data_bytes = [int(data_hex[i:i+2], 16) for i in range(0, 16, 2)]
                
                results = validator.validate_message(data_bytes, verbose=False)
                
                if not results['valid'] or results['warnings']:
                    print(f"\nMessage {i}: {row[3]}")
                    if results['errors']:
                        print("  ERRORS:", "; ".join(results['errors']))
                    if results['warnings']:
                        print("  WARNINGS:", "; ".join(results['warnings']))
    else:
        # Just show statistics
        print(f"\nValidator ready with {len(validator.checksum_lookup)} checksum entries")
        print("\nExample usage in code:")
        print("""
    # Validate a message
    message_bytes = [0x18, 0x03, 0x68, 0x00, 0x00, 0xBA, 0x25, 0x00]
    results = validator.validate_message(message_bytes)
    
    # Get expected checksum
    checksum = validator.get_checksum(0x03, 0x68, 0xBA)  # Returns 0x25
        """)
