<?php
declare(strict_types=1);

// Minimal same-origin PHP adapter for the ITP API.
// All secrets remain on the server. The browser talks only to this file.

const MAX_TURNS = 10;
const POLL_WAIT_SECONDS = 10.0;
const REQUEST_TIMEOUT_SECONDS = 20;

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');

final class ApiFailure extends RuntimeException
{
    public int $httpStatus;
    public string $errorCode;
    public ?int $retryAfterSeconds;
    /** @var array<int, array<string, mixed>>|null */
    public ?array $errors;

    /**
     * @param array<int, array<string, mixed>>|null $errors
     */
    public function __construct(
        int $httpStatus,
        string $errorCode,
        string $message,
        ?int $retryAfterSeconds = null,
        ?array $errors = null
    ) {
        parent::__construct($message);
        $this->httpStatus = $httpStatus;
        $this->errorCode = $errorCode;
        $this->retryAfterSeconds = $retryAfterSeconds;
        $this->errors = $errors;
    }
}

function respond(int $status, array $payload): never
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function fail(int $status, string $code, string $message, ?int $retryAfterSeconds = null, ?array $errors = null): never
{
    respond($status, [
        'error' => array_filter([
            'code' => $code,
            'message' => $message,
            'retryAfterSeconds' => $retryAfterSeconds,
            'errors' => $errors,
        ], static fn ($value) => $value !== null),
    ]);
}

function projectRoot(): string
{
    return dirname(__DIR__);
}

/**
 * Load a tiny .env file without external dependencies.
 *
 * @return array<string, string>
 */
function loadEnv(): array
{
    static $env = null;
    if (is_array($env)) {
        return $env;
    }

    $path = projectRoot() . DIRECTORY_SEPARATOR . '.env';
    if (!is_file($path) || !is_readable($path)) {
        fail(500, 'CONFIG_MISSING', 'The .env file is missing or not readable.');
    }

    $data = [];
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if ($lines === false) {
        fail(500, 'CONFIG_UNREADABLE', 'The .env file could not be read.');
    }

    foreach ($lines as $line) {
        $trimmed = trim($line);
        if ($trimmed === '' || str_starts_with($trimmed, '#')) {
            continue;
        }
        $pos = strpos($trimmed, '=');
        if ($pos === false) {
            continue;
        }
        $key = trim(substr($trimmed, 0, $pos));
        $value = trim(substr($trimmed, $pos + 1));
        if ($value !== '' && (($value[0] ?? '') === '"' || ($value[0] ?? '') === "'")) {
            $quote = $value[0];
            if (substr($value, -1) === $quote) {
                $value = substr($value, 1, -1);
            }
        }
        if ($key !== '') {
            $data[$key] = $value;
        }
    }

    foreach (['ITP_API_URL', 'ITP_API_KEY'] as $required) {
        if (!isset($data[$required]) || $data[$required] === '') {
            fail(500, 'CONFIG_INVALID', 'The .env file is missing the required setting ' . $required . '.');
        }
    }

    $env = $data;
    return $env;
}

function apiBaseUrl(): string
{
    $url = rtrim(loadEnv()['ITP_API_URL'], '/');
    if (!preg_match('#^https://#i', $url)) {
        fail(500, 'CONFIG_INVALID', 'ITP_API_URL must begin with https://');
    }
    return $url . '/api/v1';
}

function apiKey(): string
{
    return loadEnv()['ITP_API_KEY'];
}

function openSession(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }

    $isSecure = (
        (!empty($_SERVER['HTTPS']) && strtolower((string) $_SERVER['HTTPS']) !== 'off') ||
        (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https') ||
        (($_SERVER['SERVER_PORT'] ?? '') === '443')
    );

    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'domain' => '',
        'secure' => $isSecure,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_start();
}

/**
 * @return array{sessionId:string,agentId:string,token:string,lastAcceptedTurn:int}
 */
function activeInteraction(): array
{
    openSession();
    $itp = $_SESSION['itp'] ?? null;
    if (!is_array($itp)) {
        fail(409, 'NO_ACTIVE_INTERACTION', 'There is no active interaction. Start a new one.');
    }
    if (!isset($itp['sessionId'], $itp['agentId'], $itp['token'])) {
        unset($_SESSION['itp']);
        fail(409, 'BROKEN_SESSION', 'The local interaction session is incomplete.');
    }
    $itp['lastAcceptedTurn'] = (int) ($itp['lastAcceptedTurn'] ?? 0);
    return $itp;
}

function encodedSegment(string $value): string
{
    return rawurlencode($value);
}

/**
 * @return array<string, mixed>|list<mixed>
 */
function jsonInput(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        fail(400, 'INVALID_JSON', 'The request body must contain JSON.');
    }

    try {
        $data = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        fail(400, 'INVALID_JSON', 'The request body contains invalid JSON.');
    }

    if (!is_array($data)) {
        fail(400, 'INVALID_JSON', 'The request body must be a JSON object.');
    }

    return $data;
}

/**
 * @param mixed $value
 * @return array{Theta: float, R: float}
 */
function validIpc(mixed $value): array
{
    if (!is_array($value)) {
        fail(422, 'INVALID_BEHAVIOR', 'The behavior must be an IPC object.');
    }

    $theta = $value['Theta'] ?? null;
    $radius = $value['R'] ?? null;
    if (!is_numeric($theta) || !is_numeric($radius)) {
        fail(422, 'INVALID_BEHAVIOR', 'IPC behavior must contain numeric Theta and R values.');
    }

    $theta = (float) $theta;
    $radius = (float) $radius;
    if (!is_finite($theta) || !is_finite($radius)) {
        fail(422, 'INVALID_BEHAVIOR', 'Theta and R must be finite numbers.');
    }
    if ($radius < 0.0 || $radius > 1.0) {
        fail(422, 'INVALID_BEHAVIOR', 'R must be between 0 and 1.');
    }

    if ($radius === 0.0) {
        $theta = 0.0;
    } else {
        $theta = fmod($theta, 360.0);
        if ($theta < 0.0) {
            $theta += 360.0;
        }
    }

    return ['Theta' => $theta, 'R' => $radius];
}

/**
 * Perform an HTTP request against the ITP API.
 *
 * @param array<string, mixed>|null $payload
 * @param array<string, scalar|null> $query
 * @return array<string, mixed>|list<mixed>
 */
function itpRequest(string $method, string $path, ?array $payload = null, ?string $interactionToken = null, array $query = []): array
{
    $url = apiBaseUrl() . $path;
    if ($query !== []) {
        $url .= '?' . http_build_query($query);
    }

    $headers = [
        'Accept: application/json',
        'X-API-Key: ' . apiKey(),
    ];
    if ($interactionToken !== null) {
        $headers[] = 'Authorization: Bearer ' . $interactionToken;
    }
    if ($payload !== null) {
        $headers[] = 'Content-Type: application/json';
    }

    $curl = curl_init($url);
    if ($curl === false) {
        fail(500, 'CURL_INIT_FAILED', 'cURL could not be initialized.');
    }

    $responseHeaders = [];
    curl_setopt_array($curl, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_TIMEOUT => REQUEST_TIMEOUT_SECONDS,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_HEADERFUNCTION => static function ($curlHandle, string $headerLine) use (&$responseHeaders): int {
            $len = strlen($headerLine);
            $parts = explode(':', $headerLine, 2);
            if (count($parts) === 2) {
                $responseHeaders[strtolower(trim($parts[0]))] = trim($parts[1]);
            }
            return $len;
        },
    ]);

    if ($payload !== null) {
        // The register endpoint requires a JSON object, not an empty JSON array.
        // Encode empty request bodies as {} rather than [].
        $jsonPayload = $payload === [] ? (object) [] : $payload;
        curl_setopt($curl, CURLOPT_POSTFIELDS, json_encode($jsonPayload, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    }

    $raw = curl_exec($curl);
    $errno = curl_errno($curl);
    $error = curl_error($curl);
    $httpCode = (int) curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    curl_close($curl);

    if ($raw === false || $errno !== 0) {
        $message = 'The ITP server is currently not reachable.';
        $code = 'UPSTREAM_UNREACHABLE';

        if ($errno === 60) {
            $message = 'TLS certificate validation failed in PHP cURL (error 60). Configure curl.cainfo and openssl.cafile in php.ini.';
            $code = 'CURL_TLS_VALIDATION_FAILED';
        } elseif ($errno === 77) {
            $message = 'The CA certificate file configured for PHP cURL could not be read (error 77).';
            $code = 'CURL_CA_FILE_INVALID';
        } elseif ($errno === 6) {
            $message = 'DNS resolution failed while contacting the ITP server (error 6).';
            $code = 'CURL_DNS_FAILED';
        } elseif ($errno === 7) {
            $message = 'The connection to the ITP server could not be established (error 7).';
            $code = 'CURL_CONNECTION_FAILED';
        } elseif ($errno === 28) {
            $message = 'The request to the ITP server timed out (error 28).';
            $code = 'CURL_TIMEOUT';
        } elseif ($error !== '') {
            $message = 'The connection to the ITP server failed: ' . $error;
            $code = 'CURL_ERROR';
        }

        throw new ApiFailure(502, $code, $message);
    }

    if ($raw === '') {
        throw new ApiFailure(502, 'EMPTY_RESPONSE', 'The ITP server returned an empty response.');
    }

    try {
        $data = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    } catch (JsonException) {
        throw new ApiFailure(502, 'BAD_RESPONSE', 'The ITP server returned invalid JSON.');
    }

    if (!is_array($data)) {
        throw new ApiFailure(502, 'BAD_RESPONSE', 'The ITP server returned an unexpected response shape.');
    }

    if ($httpCode >= 400) {
        $message = is_string($data['detail'] ?? null) ? $data['detail'] : 'The ITP server rejected the request.';
        $retryAfter = isset($data['retryAfterSeconds']) && is_numeric($data['retryAfterSeconds']) ? (int) $data['retryAfterSeconds'] : null;
        $errors = is_array($data['errors'] ?? null) ? $data['errors'] : null;
        $errorCode = is_string($data['type'] ?? null) ? (string) $data['type'] : 'UPSTREAM_HTTP_' . $httpCode;
        if ($retryAfter === null && isset($responseHeaders['retry-after']) && ctype_digit($responseHeaders['retry-after'])) {
            $retryAfter = (int) $responseHeaders['retry-after'];
        }
        throw new ApiFailure($httpCode, $errorCode, $message, $retryAfter, $errors);
    }

    return $data;
}

function requireMethod(string $expected): void
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== $expected) {
        fail(405, 'METHOD_NOT_ALLOWED', 'This action requires ' . $expected . '.');
    }
}

try {
    $action = $_GET['action'] ?? '';
    if (!is_string($action)) {
        fail(400, 'INVALID_ACTION', 'Invalid action.');
    }

    switch ($action) {
        case 'start':
            requireMethod('POST');
            jsonInput(); // Intentionally require a JSON body, even though it is an empty object.
            openSession();
            unset($_SESSION['itp']); // Each start creates a fresh, non-persistent interaction.

            $created = itpRequest('POST', '/interactions', [
                'modelId' => 'lassi',
                'numberOfTurns' => MAX_TURNS,
                'startingAgentRole' => 'A',
                'persistence' => ['enabled' => false],
                'agents' => [
                    'A' => ['type' => 'model'],
                    'B' => ['type' => 'human', 'stateSpace' => 'ipc'],
                ],
            ]);
            $sid = $created['sessionId'] ?? null;
            $token = $created['interactionToken'] ?? null;
            $human = $created['agents']['B']['agentId'] ?? null;
            if (!is_string($sid) || !is_string($token) || $token === '' || !is_string($human) ||
                ($created['agents']['B']['stateSpace'] ?? null) !== 'ipc') {
                fail(502, 'UPSTREAM_INVALID_RESPONSE', 'The ITP start response did not contain a valid IPC session.');
            }

            $path = '/interactions/' . encodedSegment($sid) . '/agents/' . encodedSegment($human);
            // Register the human agent. The interaction token remains inside PHP only.
            $registered = itpRequest('POST', $path . '/register', [], $token);
            if (($registered['registrationStatus'] ?? null) !== 'registered') {
                fail(502, 'UPSTREAM_REGISTRATION_FAILED', 'The human agent could not be registered.');
            }

            $_SESSION['itp'] = [
                'sessionId' => $sid,
                'agentId' => $human,
                'token' => $token,
                'lastAcceptedTurn' => 0,
            ];
            session_write_close();
            respond(200, [
                'ok' => true,
                'sessionStatus' => $registered['sessionStatus'] ?? 'running',
                'numberOfTurns' => MAX_TURNS,
            ]);

        case 'perception':
            requireMethod('GET');
            $itp = activeInteraction();
            // Release the PHP session lock during the long-poll request.
            session_write_close();
            $after = $_GET['after'] ?? null;
            if ($after !== null && (!is_string($after) || strlen($after) > 128 || !preg_match('/^[A-Za-z0-9._~-]+$/', $after))) {
                fail(400, 'INVALID_CURSOR', 'Invalid perception cursor.');
            }
            $query = ['wait' => POLL_WAIT_SECONDS];
            if ($after !== null && $after !== '') {
                $query['after'] = $after;
            }
            $result = itpRequest(
                'GET',
                '/interactions/' . encodedSegment($itp['sessionId']) . '/agents/' . encodedSegment($itp['agentId']) . '/perception',
                null,
                $itp['token'],
                $query
            );
            $perceptionState = $result['state'] ?? null;
            if (!in_array($perceptionState, ['pending', 'perceivable', 'actionRequired', 'interactionEnded'], true)) {
                fail(502, 'UPSTREAM_INVALID_RESPONSE', 'The ITP server returned an unknown perception state.');
            }
            if ($perceptionState === 'perceivable') {
                if (!is_array($result['experience'] ?? null)) {
                    fail(502, 'UPSTREAM_INVALID_RESPONSE', 'The ITP server did not return an IPC state.');
                }
                // Validate only; the server owns the AC/IPC conversion.
                $result['experience'] = validIpc($result['experience']);
            }
            respond(200, [
                'state' => $perceptionState,
                'sessionStatus' => $result['sessionStatus'] ?? null,
                'cursor' => $result['cursor'] ?? null,
                'perceptionId' => $result['perceptionId'] ?? null,
                'turn' => $result['turn'] ?? null,
                'currentTurn' => $result['currentTurn'] ?? null,
                'actionRequired' => $result['actionRequired'] ?? ($perceptionState === 'actionRequired'),
                'experience' => $perceptionState === 'perceivable' ? $result['experience'] : null,
                'retryAfterMilliseconds' => $result['retryAfterMilliseconds'] ?? null,
                'finalTurn' => $result['finalTurn'] ?? null,
                'endReason' => $result['endReason'] ?? null,
            ]);

        case 'act':
            requireMethod('POST');
            $input = jsonInput();
            $itp = activeInteraction(); // The session lock prevents duplicate parallel submissions.
            $turn = $input['turn'] ?? null;
            $actionId = $input['actionId'] ?? null;
            if (!is_int($turn) || $turn < 1 || $turn > MAX_TURNS || !is_string($actionId) ||
                !preg_match('/^[A-Za-z0-9_-]{1,96}$/D', $actionId)) {
                fail(422, 'INVALID_ACTION', 'Invalid turn number or actionId.');
            }
            if (!is_array($input['behavior'] ?? null)) {
                fail(422, 'INVALID_BEHAVIOR', 'behavior must be an IPC object.');
            }
            $behavior = validIpc($input['behavior']);
            if ($turn <= $itp['lastAcceptedTurn']) {
                fail(409, 'ACTION_ALREADY_ACCEPTED', 'This turn has already been submitted.');
            }

            // A failed or ambiguous submission is not retried in this minimal client.
            $result = itpRequest(
                'POST',
                '/interactions/' . encodedSegment($itp['sessionId']) . '/agents/' . encodedSegment($itp['agentId']) . '/actions',
                [
                    'actionId' => $actionId,
                    'turn' => $turn,
                    'behavior' => $behavior,
                ],
                $itp['token']
            );

            if (($result['status'] ?? null) !== 'accepted' || ($result['turn'] ?? null) !== $turn) {
                fail(502, 'ACTION_OUTCOME_UNKNOWN', 'The action was not confirmed. Start a new interaction.');
            }

            $_SESSION['itp']['lastAcceptedTurn'] = $turn;
            session_write_close();
            respond(200, [
                'status' => 'accepted',
                'turn' => $turn,
                'sessionStatus' => $result['sessionStatus'] ?? 'running',
            ]);

        case 'end':
            requireMethod('POST');
            jsonInput();
            openSession();
            $itp = $_SESSION['itp'] ?? null;
            unset($_SESSION['itp']);
            session_write_close();
            if (is_array($itp) && isset($itp['sessionId'], $itp['token'])) {
                try {
                    itpRequest(
                        'POST',
                        '/interactions/' . encodedSegment($itp['sessionId']) . '/end',
                        ['reason' => 'terminatedByClient'],
                        $itp['token']
                    );
                } catch (ApiFailure) {
                    // A local reset should not fail just because the upstream session already expired.
                }
            }
            respond(200, ['ok' => true]);

        default:
            fail(404, 'UNKNOWN_ACTION', 'Unknown API action.');
    }
} catch (ApiFailure $error) {
    respond($error->httpStatus, [
        'error' => array_filter([
            'code' => $error->errorCode,
            'message' => $error->getMessage(),
            'retryAfterSeconds' => $error->retryAfterSeconds,
            'errors' => $error->errors,
        ], static fn ($value) => $value !== null),
    ]);
} catch (Throwable) {
    respond(500, ['error' => ['code' => 'INTERNAL_ERROR', 'message' => 'Internal server error.']]);
}
