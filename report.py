import json
from typing import Any, Dict, List, Set
import os

LAMPORTS_PER_SOL = 1_000_000_000


class SolanaTransactionAnalyzer:
    KNOWN_PROGRAMS = {
    "11111111111111111111111111111111": "System Program",
    "Stake11111111111111111111111111111111111111": "Stake Program",
    "Vote111111111111111111111111111111111111111": "Vote Program",
    "BPFLoader1111111111111111111111111111111111": "BPF Loader",
    "BPFLoader2111111111111111111111111111111111": "BPF Loader 2",
    "BPFLoaderUpgradeab1e11111111111111111111111": "Upgradeable BPF Loader",
    "Config1111111111111111111111111111111111111": "Config Program",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "SPL Token Program",
    "ATokenGPvbdGVxr1cZ6Gh8RQzeyG3kG9FZ6Vf9eTGzH": "Associated Token Program",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo Program",
    "NamesLPvCLsAGdkd9H9Yw2BTdh6aZq8aJgzQq5xTMvR": "Bonfida Name Service",
    "C98vHVgGJHD5kz7Z2GUak3hXwLMi9cTzGE5GQ5NB5yQf": "Coin98 Swap",
    "DEX11111111111111111111111111111111111111": "Serum DEX v1",
    "9xQeWvG816bUx9EP1xQPLvAd9ESGZ1uP7m7bRMkUU7zN": "Serum DEX v3",
    "4ckmDgGzLyD5G9uv6C6p2XpWwFqXRqVgTxNTG9c9tk4C": "Solend",
    "EhhTKjxyMiRgnJp1HZFHyhEHEcCeURhfMSyjYbw1EKn": "Mango Markets",
    "F9bUkWQi9Uu5FeFSGDqJ8H3gXbFS8A7tBzUVnHyKNxy": "Raydium Swap",
    }


    def __init__(self, tx_data: Dict[str, Any], position: int, total: int, verbose: bool = False):
        self.tx_data = tx_data
        self.position = position
        self.total = total
        self.verbose = verbose
        self.summary = []
        self.total_transferred = 0
        self.transfer_count = 0
        self.involved_accounts: Set[str] = set()

    def analyze(self) -> str:
        self._add_header()
        self._analyze_instructions()
        self._analyze_inner_instructions()
        self._add_summary()
        report = "\n".join(self.summary)
        if self.verbose:
            print(report)
        return report

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
        program_id = instr.get("programId", {}).get("address") or instr.get("programId", "Unknown")
        program = self.KNOWN_PROGRAMS.get(program_id, program_id)
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
                            decimals = details.get("decimals", 9)
                            display_amount = amount / (10 ** decimals)
                            val_str += f" ({display_amount:.6f})"
                            self.total_transferred += amount
                            self.transfer_count += 1
                        except Exception:
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

        if self.involved_accounts:
            self.summary.append("Involved Accounts:")
            for acc in sorted(self.involved_accounts):
                self.summary.append(f" - {acc}")

        pre = self.tx_data.get("meta", {}).get("preBalances", [])
        post = self.tx_data.get("meta", {}).get("postBalances", [])
        if pre and post and len(pre) == len(post):
            self.summary.append("\nBalance Changes:")
            for i, (pre_bal, post_bal) in enumerate(zip(pre, post)):
                delta = post_bal - pre_bal
                if delta != 0:
                    self.summary.append(f" - Account {i} Δ Balance: {delta:+,} lamports ({delta / LAMPORTS_PER_SOL:+.6f} SOL)")


# --- Utility functions ---

def load_transaction(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r') as f:
        return [json.loads(line) for line in f]

def save_report(text: str, output_path: str):
    with open(output_path, 'a') as f:
        f.write(text)

def create_report_sandwich(input_file: str, verbose: bool = False) -> str:
    output_file = "transaction_report.txt"
    try:
        tx_data = load_transaction(input_file)
        total_transactions = len(tx_data)

        for idx, entry in enumerate(tx_data, 1):
            analyzer = SolanaTransactionAnalyzer(entry, idx, total_transactions, verbose=verbose)
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
