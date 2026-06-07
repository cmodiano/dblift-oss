#!/bin/bash
# Setup script for DBLift documentation with MkDocs

set -e

echo "🚀 Setting up DBLift documentation with MkDocs..."

# Check if we're in the right directory
if [ ! -f "setup.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Install dependencies
echo "📦 Installing MkDocs and dependencies..."
pip install mkdocs mkdocs-material mkdocstrings[python] pymdown-extensions

# Create docs structure if it doesn't exist
echo "📁 Creating documentation structure..."
mkdir -p docs/user-guide
mkdir -p docs/api-reference
mkdir -p docs/architecture
mkdir -p docs/development
mkdir -p docs/examples
mkdir -p docs/advanced

# Copy example config if mkdocs.yml doesn't exist
if [ ! -f "mkdocs.yml" ]; then
    if [ -f "mkdocs.yml.example" ]; then
        echo "📋 Creating mkdocs.yml from example..."
        cp mkdocs.yml.example mkdocs.yml
        echo "✅ Created mkdocs.yml - please review and customize it"
    else
        echo "⚠️  mkdocs.yml.example not found, creating basic mkdocs.yml..."
        cat > mkdocs.yml << 'EOF'
site_name: DBLift Documentation
site_description: Database migration tool documentation

theme:
  name: material

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          paths: [.]

nav:
  - Home: index.md
EOF
    fi
else
    echo "✅ mkdocs.yml already exists"
fi

# Create index.md if it doesn't exist
if [ ! -f "docs/index.md" ]; then
    if [ -f "docs/index.md.example" ]; then
        echo "📄 Creating docs/index.md from example..."
        cp docs/index.md.example docs/index.md
    else
        echo "📄 Creating basic docs/index.md..."
        cat > docs/index.md << 'EOF'
# DBLift Documentation

Welcome to DBLift documentation!

## Quick Links

- [User Guide](user-guide/getting-started.md)
- [API Reference](api-reference/api/client.md)
- [Architecture](architecture/overview.md)
EOF
    fi
fi

echo ""
echo "✅ Documentation setup complete!"
echo ""
echo "Next steps:"
echo "  1. Review and customize mkdocs.yml"
echo "  2. Organize existing documentation into the new structure"
echo "  3. Run 'mkdocs serve' to preview locally"
echo "  4. Run 'mkdocs build' to generate static site"
echo ""
echo "Useful commands:"
echo "  mkdocs serve          # Start local server at http://127.0.0.1:8000"
echo "  mkdocs build          # Build static site in 'site/' directory"
echo "  mkdocs gh-deploy      # Deploy to GitHub Pages"
