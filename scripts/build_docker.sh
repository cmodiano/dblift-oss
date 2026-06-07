#!/bin/bash
# Script to build and test DBLift Docker image locally

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="dblift"
IMAGE_TAG="local"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${GREEN}=== DBLift Docker Build Script ===${NC}"
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

echo -e "${YELLOW}📦 Building Docker image: ${FULL_IMAGE}${NC}"
echo

# Build the image
docker build -t "${FULL_IMAGE}" .

if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
    echo
else
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
fi

# Get image size
IMAGE_SIZE=$(docker images "${FULL_IMAGE}" --format "{{.Size}}")
echo -e "${GREEN}📊 Image size: ${IMAGE_SIZE}${NC}"
echo

# Test the image
echo -e "${YELLOW}🧪 Testing Docker image...${NC}"
echo

# Test 1: Version command
echo "Test 1: --version"
if docker run --rm "${FULL_IMAGE}" --version; then
    echo -e "${GREEN}✅ Version test passed${NC}"
else
    echo -e "${RED}❌ Version test failed${NC}"
    exit 1
fi

echo

# Test 2: Help command
echo "Test 2: --help"
if docker run --rm "${FULL_IMAGE}" --help > /dev/null; then
    echo -e "${GREEN}✅ Help test passed${NC}"
else
    echo -e "${RED}❌ Help test failed${NC}"
    exit 1
fi

echo

# Summary
echo -e "${GREEN}=== Build Summary ===${NC}"
echo "Image: ${FULL_IMAGE}"
echo "Size: ${IMAGE_SIZE}"
echo
echo "To use this image:"
echo "  docker run --rm -v \$(pwd):/workspace ${FULL_IMAGE} --help"
echo
echo "To create an alias:"
echo "  alias dblift='docker run --rm -v \$(pwd):/workspace ${FULL_IMAGE}'"
echo
echo -e "${GREEN}✅ All tests passed!${NC}"

