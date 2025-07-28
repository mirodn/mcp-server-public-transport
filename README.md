# mcp-server-public-transport

An MCP-compatible server providing real-time public transport data across Europe.

## About

mcp-server-public-transport is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction)-compatible local server that provides access to public transport data across Europe.
Currently, it integrates APIs from UK, Switzerland and Belgium, allowing you to retrieve train connections, live departures, and bus locations.

## Feature Implementation Status

### Supported Countries

| Country               | API Base URL                                                     | Status |
| --------------------- | ---------------------------------------------------------------- | ------ |
| **United Kingdom**    | [https://transportapi.com](https://transportapi.com)             | 🟡  (API key issues) |
| **Switzerland**       | [https://transport.opendata.ch](https://transport.opendata.ch)   | ✅     |
| **Belgium**           | [https://api.irail.be](https://api.irail.be)                      | ✅     |

### Features by Country

| Feature               | API Path                                                        | Status |
| --------------------- | --------------------------------------------------------------- | ------ |
| **United Kingdom** |   |   |
| Live Departures | `/uk/train/station/{station_code}/live.json`        | 🟡 (API key issues) |
| **Switzerland** | | |
| Search Connections | `/connections`                    | ✅     |
| Station Lookup     | `/locations`                      | ✅     |
| Departure Board    | `/stationboard`                   | ✅     |
| Nearby Stations    | `/locations?x={lon}&y={lat}`      | ✅     |
| **Belgium**           |                                |        |
| Live Departures | `/departures`                   | ✅     |
| Station Lookup     | `/stations`                     | ✅     |
| Nearby Stations    | `/stations/nearby`              | ✅     |

## Setup

### Environment Variables

Set the following environment variables:

```plaintext
UK_TRANSPORT_APP_ID=your_uk_app_id
UK_TRANSPORT_API_KEY=your_uk_api_key
```

### Usage with Claude Desktop

Add to your claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-server-public-transport": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/mcp-server-public-transport",
        "run",
        "server.py"
      ],
      "env": {
        "UK_TRANSPORT_APP_ID": "your-uk-app-id",
        "UK_TRANSPORT_API_KEY": "your-uk-api-key"
      }
    }
  }
}

```

Replace `/ABSOLUTE/PATH/TO/PARENT/FOLDER/mcp-server-public-transport` with the actual path where you've cloned the repository.
> Note: You may need to put the full path to the uv executable in the command field. You can get this by running which uv on MacOS/Linux or where uv on Windows.

## Development

### Setting up Development Environment

1. **Clone the repository**

   ```bash
   git clone https://github.com/mirodn/mcp-server-public-transport.git
   cd mcp-server-public-transport
    ```

2. **Install dependencies**

    ```bash
    uv sync
    ```

3. **Set environment variables**

    ```bash
    cp .env.example .env
    ```

4. **Run the server**

    ```bash
    uv run server.py
    ```

### Running Tests

The project uses pytest for testing with the following commands available:

```bash
# Run all tests
make test
```

### Code Quality

```bash
# Run linting
make lint

# Run code formatting
make format
```

### Continuous Integration

The project includes a GitHub Actions workflow (`.github/workflows/test.yml`) that automatically:

- Runs tests on Python 3.10, 3.11, and 3.12
- Executes linting checks using ruff
- Runs on every push and pull request to `main` branch

The CI pipeline ensures code quality and compatibility across supported Python versions before any changes are merged.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

The package is deployed automatically to PyPI when project.version is updated in `pyproject.toml`.
Follow semver for versioning.

## License

[MIT License](LICENSE)
