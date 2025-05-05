import json
from typing import Any, Dict, List, Set
import os

LAMPORTS_PER_SOL = 1_000_000_000


class SolanaTransactionAnalyzer:
    def __init__(self, tx_data: Dict[str, Any], position: int, total: int):
        self.tx_data = tx_data
        self.position = position
        self.total = total
        self.summary = []
        self.total_transferred = 0
        self.transfer_count = 0
        self.involved_accounts: Set[str] = set()

    def analyze(self) -> str:
        self._add_header()
        self._analyze_instructions()
        self._analyze_inner_instructions()
        self._add_summary()
        return "\n".join(self.summary)

    def _add_header(self):
        report_prefix = "\n\nSolana Transaction Report"

        if self.position == 1:
            report_prefix += " - Front Running"
        elif self.position == self.total:
            report_prefix += " - Back Running"
        else:
            report_prefix += " - Victim"

        self.summary.append(report_prefix)
        self.summary.append("=" * 40)
        self.summary.append(f"Transaction Hash: {self.tx_data.get('transactionHash', 'N/A')}")
        self.summary.append(f"Block Number:     {self.tx_data.get('blockNumber', 'N/A')}")
        fee = self.tx_data.get("meta", {}).get("fee", 0)
        self.summary.append(f"Transaction Fee:  {fee:,} lamports ({fee / LAMPORTS_PER_SOL:.6f} SOL)")
        self.summary.append("=" * 40)

    def _analyze_instructions(self):
        instructions = self.tx_data.get("instructions", [])
        for idx, instr in enumerate(instructions, 1):
            self.summary.append(f"\nInstruction {idx}:")
            self._describe_instruction(instr)

    def _analyze_inner_instructions(self):
        inner = self.tx_data.get("meta", {}).get("innerInstructions", [])
        if not inner:
            return
        self.summary.append("\nInner Instructions:")
        for parent_idx, group in enumerate(inner, 1):
            for idx, instr in enumerate(group.get("instructions", []), 1):
                self.summary.append(f"\n  ↪ Inner Instruction {parent_idx}.{idx}:")
                self._describe_instruction(instr, indent="    ")

    def _describe_instruction(self, instr: Dict[str, Any], indent: str = "  "):
        program = instr.get("programId", {}).get("name") or instr.get("program", "Unknown Program")
        self.summary.append(f"{indent}Program: {program}")

        parsed = instr.get("parsed")
        if parsed:
            for action, details in parsed.items():
                self.summary.append(f"{indent}Action: {action}")
                for key, val in details.items():
                    val_str = self._format_value(val)
                    if key in ["lamports", "amount"]:
                        try:
                            amount = int(val)
                            sol = amount / LAMPORTS_PER_SOL
                            val_str += f" ({sol:.6f} SOL)"
                            self.total_transferred += amount
                            self.transfer_count += 1
                        except:
                            pass
                    elif key in ["source", "destination", "owner", "authority"]:
                        self.involved_accounts.add(str(val))
                    self.summary.append(f"{indent}   - {key}: {val_str}")
        else:
            # Unparsed instructions
            accounts = instr.get("accounts", [])
            if accounts:
                self.summary.append(f"{indent}Accounts: {', '.join(accounts)}")
                self.involved_accounts.update(accounts)
            data = instr.get("data", "N/A")
            self.summary.append(f"{indent}Data (raw): {data}")

    def _format_value(self, val: Any) -> str:
        if isinstance(val, dict) and "address" in val:
            return val["address"]
        elif isinstance(val, list):
            return ", ".join(self._format_value(item) for item in val)
        else:
            return str(val)

    def _add_summary(self):
        self.summary.append("\nTransaction Summary:")
        self.summary.append("-" * 25)
        self.summary.append(f"Total Transfers:   {self.transfer_count}")
        self.summary.append(f"Total Moved:       {self.total_transferred:,} lamports ({self.total_transferred / LAMPORTS_PER_SOL:.6f} SOL)")
        self.summary.append(f"Accounts Involved: {len(self.involved_accounts)}")


# --- Utility functions ---

def load_transaction(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r') as f:
        return [json.loads(line) for line in f]

def save_report(text: str, output_path: str):
    with open(output_path, 'a') as f:
        f.write(text)

def create_report_sandwich(input_file: str) -> str:
    output_file = "transaction_report.txt"
    try:
        tx_data = load_transaction(input_file)
        total_transactions = len(tx_data)

        for idx, entry in enumerate(tx_data, 1):
            analyzer = SolanaTransactionAnalyzer(entry, idx, total_transactions)
            report = analyzer.analyze()
            save_report(report, output_file)

        with open(output_file, "r") as file:
            final_report = file.read()

        os.remove(output_file)
        os.remove(input_file)

        return final_report

    except Exception as e:
        print(f"❌ Error: {e}")
        return ""
