#!/bin/bash
# Build and validate the package for PyPI

set -e  # Exit on error

echo "==========================================="
echo "Open-Skills PyPI Build & Validation"
echo "==========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Clean previous builds
echo -e "${YELLOW}[1/6] Cleaning previous builds...${NC}"
rm -rf build/ dist/ *.egg-info
echo -e "${GREEN}✓ Clean complete${NC}"
echo ""

# Step 2: Run tests
echo -e "${YELLOW}[2/6] Running tests...${NC}"
if command -v pytest &> /dev/null; then
    pytest tests/ -v --tb=short || {
        echo -e "${RED}✗ Tests failed${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Tests passed${NC}"
else
    echo -e "${YELLOW}⚠ pytest not installed, skipping tests${NC}"
fi
echo ""

# Step 3: Check code quality
echo -e "${YELLOW}[3/6] Checking code quality...${NC}"
if command -v ruff &> /dev/null; then
    ruff check open_skills/ || {
        echo -e "${RED}✗ Linting failed${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Code quality checks passed${NC}"
else
    echo -e "${YELLOW}⚠ ruff not installed, skipping linting${NC}"
fi
echo ""

# Step 4: Build the package
echo -e "${YELLOW}[4/6] Building package...${NC}"
python -m build || {
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Step 5: Verify package contents
echo -e "${YELLOW}[5/6] Verifying package contents...${NC}"
echo "Distribution files:"
ls -lh dist/
echo ""

# Check tarball contents
echo "Source distribution contents (first 30 files):"
tar -tzf dist/open_skills-*.tar.gz | head -30
echo "..."
echo ""

# Check wheel contents
echo "Wheel contents (first 30 files):"
unzip -l dist/open_skills-*.whl | head -30
echo "..."
echo ""

# Step 6: Validate package with twine
echo -e "${YELLOW}[6/6] Validating with twine...${NC}"
if command -v twine &> /dev/null; then
    twine check dist/* || {
        echo -e "${RED}✗ Package validation failed${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Package validation passed${NC}"
else
    echo -e "${YELLOW}⚠ twine not installed, install with: pip install twine${NC}"
fi
echo ""

echo "==========================================="
echo -e "${GREEN}✓ Build & Validation Complete!${NC}"
echo "==========================================="
echo ""
echo "Next steps:"
echo "1. Test on TestPyPI:"
echo "   twine upload --repository testpypi dist/*"
echo ""
echo "2. Install from TestPyPI:"
echo "   pip install --index-url https://test.pypi.org/simple/ open-skills"
echo ""
echo "3. Publish to PyPI:"
echo "   twine upload dist/*"
echo ""
echo "See PUBLISHING.md for detailed instructions."
