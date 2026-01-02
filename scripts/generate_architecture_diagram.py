#!/usr/bin/env python3
"""Generate Mermaid architecture diagram from Python codebase.

This script analyzes the codebase structure and generates a Mermaid diagram
showing the three-layer architecture (top/middle/bottom).
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple


class FunctionInfo(NamedTuple):
    """Information about a function."""

    name: str
    module: str
    is_method: bool
    calls: list[str]
    complexity: int  # Simple estimate based on statements


class CodeAnalyzer:
    """Analyze Python code structure."""

    def __init__(self, root_dir: Path):
        """Initialize analyzer.

        Args:
            root_dir: Root directory of the codebase.
        """
        self.root_dir = root_dir
        self.functions = []
        self.classes = {}

    def analyze(self):
        """Analyze all Python files in the codebase."""
        # Find all Python files
        py_files = list(self.root_dir.rglob("*.py"))
        py_files = [f for f in py_files if "test" not in str(f) and "__pycache__" not in str(f)]

        for py_file in py_files:
            self._analyze_file(py_file)

    def _analyze_file(self, file_path: Path):
        """Analyze a single Python file.

        Args:
            file_path: Path to the Python file.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))
        except Exception as e:
            print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)
            return

        module_name = self._get_module_name(file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check if it's a method or standalone function
                parent = self._get_parent_class(tree, node)
                is_method = parent is not None

                # Extract function calls
                calls = self._extract_calls(node)

                # Estimate complexity
                complexity = len(list(ast.walk(node)))

                func_info = FunctionInfo(
                    name=node.name,
                    module=module_name,
                    is_method=is_method,
                    calls=calls,
                    complexity=complexity,
                )
                self.functions.append(func_info)

            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = {
                    "module": module_name,
                    "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                }

    def _get_module_name(self, file_path: Path) -> str:
        """Get module name from file path.

        Args:
            file_path: Path to the Python file.

        Returns:
            Module name (e.g., 'docfiler.config').
        """
        rel_path = file_path.relative_to(self.root_dir)
        parts = list(rel_path.parts[:-1]) + [rel_path.stem]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _get_parent_class(self, tree, func_node):
        """Get parent class of a function if it's a method."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if func_node in node.body:
                    return node.name
        return None

    def _extract_calls(self, func_node) -> list[str]:
        """Extract function calls from a function."""
        calls = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        return calls

    def categorize_by_layer(self) -> dict:
        """Categorize functions into top/middle/bottom layers.

        Returns:
            Dict with 'top', 'middle', 'bottom' keys.
        """
        layers = {"top": [], "middle": [], "bottom": []}

        for func in self.functions:
            # Top layer: main entry points, low complexity, few calls to internal functions
            if func.name in ("main", "__init__", "run"):
                layers["top"].append(func)

            # Bottom layer: small utility functions, no external calls
            elif func.complexity < 50 and (
                func.name.startswith("_") or len(func.calls) < 3
            ):
                layers["bottom"].append(func)

            # Middle layer: everything else
            else:
                layers["middle"].append(func)

        return layers


class MermaidGenerator:
    """Generate Mermaid diagrams from code analysis."""

    def __init__(self, analyzer: CodeAnalyzer):
        """Initialize generator.

        Args:
            analyzer: Code analyzer instance.
        """
        self.analyzer = analyzer

    def generate_layer_diagram(self) -> str:
        """Generate layer architecture diagram.

        Returns:
            Mermaid diagram as string.
        """
        layers = self.analyzer.categorize_by_layer()

        lines = ["```mermaid", "graph TB"]

        # Group by module
        modules = {}
        for layer_name, funcs in layers.items():
            for func in funcs:
                module = func.module.split(".")[0] if "." in func.module else func.module
                if module not in modules:
                    modules[module] = {"top": [], "middle": [], "bottom": []}
                modules[module][layer_name].append(func)

        # Generate subgraphs for each module
        for module, module_layers in sorted(modules.items()):
            if module in ("tests", "__pycache__"):
                continue

            lines.append(f'    subgraph "{module}"')

            # Top layer
            if module_layers["top"]:
                lines.append('        subgraph "Top Layer (Entry Points)"')
                for func in module_layers["top"][:5]:  # Limit to 5
                    func_id = f"{module}_{func.name}".replace(".", "_")
                    lines.append(f'            {func_id}["{func.name}()"]')
                lines.append("        end")

            # Middle layer
            if module_layers["middle"]:
                lines.append('        subgraph "Middle Layer (Business Logic)"')
                for func in module_layers["middle"][:5]:  # Limit to 5
                    func_id = f"{module}_{func.name}".replace(".", "_")
                    lines.append(f'            {func_id}["{func.name}()"]')
                lines.append("        end")

            # Bottom layer
            if module_layers["bottom"]:
                lines.append('        subgraph "Bottom Layer (Utilities)"')
                for func in module_layers["bottom"][:5]:  # Limit to 5
                    func_id = f"{module}_{func.name}".replace(".", "_")
                    lines.append(f'            {func_id}["{func.name}()"]:::utility')
                lines.append("        end")

            lines.append("    end")
            lines.append("")

        # Add style
        lines.append("    classDef utility fill:#e1f5ff,stroke:#01579b")

        lines.append("```")
        return "\n".join(lines)

    def generate_module_diagram(self) -> str:
        """Generate module-level architecture diagram.

        Returns:
            Mermaid diagram as string.
        """
        lines = ["```mermaid", "graph LR"]

        # Group functions by module
        modules = {}
        for func in self.analyzer.functions:
            module = func.module
            if module not in modules:
                modules[module] = []
            modules[module].append(func)

        # Add module nodes
        for module in sorted(modules.keys()):
            if "test" in module or "__pycache__" in module:
                continue

            module_id = module.replace(".", "_")
            # Count functions in module
            func_count = len(modules[module])
            class_count = len([c for c, info in self.analyzer.classes.items()
                              if info["module"] == module])

            label = f"{module}\\n({func_count} funcs, {class_count} classes)"
            lines.append(f'    {module_id}["{label}"]')

        # Add relationships based on imports (simplified)
        lines.append("")
        lines.append("    %% Module relationships")

        # Identify core modules
        core_modules = ["docfiler.config", "docfiler.api_clients",
                       "docfiler.image_processor", "docfiler.vlm_service"]

        for core_module in core_modules:
            if core_module in modules:
                core_id = core_module.replace(".", "_")

                # GUI and CLI depend on services
                if "docfiler.gui" in modules or "docfiler.cli" in modules:
                    if core_module in ["docfiler.vlm_service", "docfiler.image_processor"]:
                        if "docfiler.gui" in modules:
                            lines.append(f"    docfiler_gui_main_window --> {core_id}")
                        if "docfiler.cli" in modules:
                            lines.append(f"    docfiler_cli_context_generator --> {core_id}")

                # Services depend on config
                if core_module == "docfiler.config":
                    for svc in ["docfiler.vlm_service", "docfiler.api_clients",
                               "docfiler.image_processor"]:
                        if svc in modules:
                            svc_id = svc.replace(".", "_")
                            lines.append(f"    {svc_id} --> {core_id}")

        lines.append("```")
        return "\n".join(lines)

    def generate_class_diagram(self) -> str:
        """Generate class diagram.

        Returns:
            Mermaid class diagram as string.
        """
        lines = ["```mermaid", "classDiagram"]

        # Add classes
        for class_name, info in sorted(self.analyzer.classes.items()):
            if "test" in info["module"].lower():
                continue

            lines.append(f"    class {class_name} {{")

            # Add methods (limit to important ones)
            public_methods = [m for m in info["methods"] if not m.startswith("_")]
            for method in public_methods[:5]:
                lines.append(f"        +{method}()")

            if len(public_methods) > 5:
                lines.append(f"        +... ({len(public_methods) - 5} more)")

            lines.append("    }")
            lines.append("")

        # Add relationships (simplified)
        lines.append("    %% Relationships")

        # VLMService uses ImageProcessor and APIClient
        if "VLMService" in self.analyzer.classes:
            if "ImageProcessor" in self.analyzer.classes:
                lines.append("    VLMService --> ImageProcessor : uses")
            if "ClaudeClient" in self.analyzer.classes:
                lines.append("    VLMService --> VLMClient : uses")

        # GUI uses VLMService
        if "MainWindow" in self.analyzer.classes and "VLMService" in self.analyzer.classes:
            lines.append("    MainWindow --> VLMService : uses")

        lines.append("```")
        return "\n".join(lines)


def main():
    """Main entry point."""
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Analyze codebase
    print("Analyzing codebase...")
    analyzer = CodeAnalyzer(project_root / "docfiler")
    analyzer.analyze()

    print(f"Found {len(analyzer.functions)} functions and {len(analyzer.classes)} classes")

    # Generate diagrams
    generator = MermaidGenerator(analyzer)

    # Generate layer diagram
    print("\n" + "=" * 50)
    print("LAYER ARCHITECTURE DIAGRAM")
    print("=" * 50)
    layer_diagram = generator.generate_layer_diagram()
    print(layer_diagram)

    # Generate module diagram
    print("\n" + "=" * 50)
    print("MODULE ARCHITECTURE DIAGRAM")
    print("=" * 50)
    module_diagram = generator.generate_module_diagram()
    print(module_diagram)

    # Generate class diagram
    print("\n" + "=" * 50)
    print("CLASS DIAGRAM")
    print("=" * 50)
    class_diagram = generator.generate_class_diagram()
    print(class_diagram)

    # Save to file
    output_file = project_root / "llms" / "architecture_diagrams.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Auto-Generated Architecture Diagrams\n\n")
        f.write("> Generated by scripts/generate_architecture_diagram.py\n\n")
        f.write(f"> Total: {len(analyzer.functions)} functions, {len(analyzer.classes)} classes\n\n")
        f.write("---\n\n")

        f.write("## Layer Architecture\n\n")
        f.write(layer_diagram)
        f.write("\n\n---\n\n")

        f.write("## Module Architecture\n\n")
        f.write(module_diagram)
        f.write("\n\n---\n\n")

        f.write("## Class Diagram\n\n")
        f.write(class_diagram)
        f.write("\n")

    print(f"\n✅ Diagrams saved to {output_file}")


if __name__ == "__main__":
    main()
