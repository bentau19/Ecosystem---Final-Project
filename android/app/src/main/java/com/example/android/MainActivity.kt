package com.example.android

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Bundle
import android.text.format.Formatter
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.android.ui.theme.AndroidTheme
import com.example.tausync_lib.implementations.management.TauSyncStream
import com.example.tausync_lib.sdk.TauSync
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AndroidTheme {
                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = MaterialTheme.colorScheme.background
                ) { innerPadding ->
                    TauSyncTestScreen(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

// ── State model ───────────────────────────────────────────────────────

private data class LogEntry(val timestamp: String, val message: String)

private data class TestResult(val name: String, val passed: Boolean?, val durationMs: Long = 0)

// ── Main test screen ──────────────────────────────────────────────────

@Composable
fun TauSyncTestScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var ipAddress by remember { mutableStateOf("192.168.1.76") }
    var connectionStatus by remember { mutableStateOf("Disconnected") }
    var tau by remember { mutableStateOf<TauSync?>(null) }
    var activeStream by remember { mutableStateOf<TauSyncStream?>(null) }

    var meetingWord by remember { mutableStateOf("main") }
    var sendMessage by remember { mutableStateOf("Hello from Android!") }
    var receivedMessage by remember { mutableStateOf("") }

    val logs = remember { mutableStateListOf<LogEntry>() }
    val testResults = remember { mutableStateListOf<TestResult>() }
    var testsRunning by remember { mutableStateOf(false) }

    val logListState = rememberLazyListState()
    val localIp = remember { getLocalIpAddress(context) }

    fun log(msg: String) {
        val ts = SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date())
        logs.add(LogEntry(ts, msg))
        scope.launch { logListState.animateScrollToItem(logs.size - 1) }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // ── Header ────────────────────────────────────────────────
        Text(
            text = "TauSync Test",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Local IP: $localIp",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline
        )

        // ── Connection section ────────────────────────────────────
        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = ipAddress,
                        onValueChange = { ipAddress = it },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        label = { Text("Server IP") },
                        enabled = tau == null
                    )
                    Button(
                        onClick = {
                            if (tau != null) {
                                scope.launch(Dispatchers.IO) {
                                    try {
                                        activeStream?.close()
                                        tau?.dispose()
                                    } catch (_: Exception) {}
                                    withContext(Dispatchers.Main) {
                                        tau = null
                                        activeStream = null
                                        connectionStatus = "Disconnected"
                                        log("Disconnected")
                                    }
                                }
                            } else {
                                connectionStatus = "Connecting..."
                                log("Connecting to $ipAddress...")
                                scope.launch(Dispatchers.IO) {
                                    try {
                                        val t = TauSync()
                                        t.connectTo(ipAddress.trim())
                                        withContext(Dispatchers.Main) {
                                            tau = t
                                            connectionStatus = "Connected to $ipAddress"
                                            log("Connected!")
                                        }
                                    } catch (e: Exception) {
                                        val rootCause = generateSequence<Throwable>(e) { it.cause }.last()
                                        withContext(Dispatchers.Main) {
                                            connectionStatus = "Failed: ${rootCause.message}"
                                            log("Connection failed: ${e.javaClass.simpleName}: ${e.message}")
                                            log("  Root cause: ${rootCause.javaClass.simpleName}: ${rootCause.message}")
                                        }
                                    }
                                }
                            }
                        },
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text(if (tau != null) "Disconnect" else "Connect")
                    }
                }
                StatusBadge(connectionStatus)
            }
        }

        // ── Manual test section ───────────────────────────────────
        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Manual Test", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)

                OutlinedTextField(
                    value = meetingWord,
                    onValueChange = { meetingWord = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Meeting Word") },
                    enabled = tau != null && activeStream == null
                )

                Button(
                    onClick = {
                        val t = tau ?: return@Button
                        if (activeStream != null) {
                            scope.launch(Dispatchers.IO) {
                                try { activeStream?.close() } catch (_: Exception) {}
                                withContext(Dispatchers.Main) {
                                    activeStream = null
                                    log("Channel closed")
                                }
                            }
                        } else {
                            log("Opening channel \"$meetingWord\"...")
                            scope.launch(Dispatchers.IO) {
                                try {
                                    val s = t.connect(meetingWord.trim())
                                    withContext(Dispatchers.Main) {
                                        activeStream = s
                                        log("Channel \"$meetingWord\" opened (ID=${s.localId})")
                                    }
                                } catch (e: Exception) {
                                    val rootCause = generateSequence<Throwable>(e) { it.cause }.last()
                                    withContext(Dispatchers.Main) {
                                        log("Open channel failed: ${e.message}")
                                        log("  Root cause: ${rootCause.javaClass.simpleName}: ${rootCause.message}")
                                    }
                                }
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = tau != null,
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(if (activeStream != null) "Close Channel" else "Open Channel")
                }

                OutlinedTextField(
                    value = sendMessage,
                    onValueChange = { sendMessage = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Message") },
                    enabled = activeStream != null
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = {
                            val s = activeStream ?: return@Button
                            val msg = sendMessage
                            scope.launch(Dispatchers.IO) {
                                try {
                                    s.writeString(msg + "\n")
                                    withContext(Dispatchers.Main) { log("Sent: $msg") }
                                } catch (e: Exception) {
                                    withContext(Dispatchers.Main) { log("Send error: ${e.message}") }
                                }
                            }
                        },
                        modifier = Modifier.weight(1f),
                        enabled = activeStream != null,
                        shape = RoundedCornerShape(8.dp)
                    ) { Text("Send") }

                    OutlinedButton(
                        onClick = {
                            val s = activeStream ?: return@OutlinedButton
                            scope.launch(Dispatchers.IO) {
                                try {
                                    val line = s.readLine()
                                    withContext(Dispatchers.Main) {
                                        receivedMessage = line ?: "<EOF>"
                                        log("Received: $receivedMessage")
                                    }
                                } catch (e: Exception) {
                                    withContext(Dispatchers.Main) { log("Read error: ${e.message}") }
                                }
                            }
                        },
                        modifier = Modifier.weight(1f),
                        enabled = activeStream != null,
                        shape = RoundedCornerShape(8.dp)
                    ) { Text("Read Line") }
                }

                if (receivedMessage.isNotEmpty()) {
                    Text(
                        text = "Received: $receivedMessage",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }
        }

        // ── Automated tests section ───────────────────────────────
        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Automated Tests", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)

                Button(
                    onClick = {
                        val t = tau ?: return@Button
                        testsRunning = true
                        testResults.clear()
                        scope.launch(Dispatchers.IO) {
                            runAutomatedTests(t, testResults, ::log)
                            withContext(Dispatchers.Main) { testsRunning = false }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = tau != null && !testsRunning,
                    shape = RoundedCornerShape(8.dp)
                ) {
                    if (testsRunning) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("Running...")
                    } else {
                        Text("Run All Tests")
                    }
                }

                testResults.forEach { result ->
                    TestResultRow(result)
                }
            }
        }

        // ── Log section ───────────────────────────────────────────
        Text("Log", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(
                    MaterialTheme.colorScheme.surfaceVariant,
                    RoundedCornerShape(8.dp)
                )
                .padding(8.dp),
            state = logListState
        ) {
            items(logs) { entry ->
                Text(
                    text = "[${entry.timestamp}] ${entry.message}",
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    lineHeight = 15.sp
                )
            }
        }
    }
}

// ── UI components ─────────────────────────────────────────────────────

@Composable
private fun StatusBadge(status: String) {
    val color = when {
        status.startsWith("Connected") -> MaterialTheme.colorScheme.primary
        status.startsWith("Connecting") -> MaterialTheme.colorScheme.tertiary
        status.startsWith("Failed") -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.outline
    }
    Text(text = "Status: $status", color = color, style = MaterialTheme.typography.bodySmall)
}

@Composable
private fun TestResultRow(result: TestResult) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(result.name, style = MaterialTheme.typography.bodyMedium)
        when (result.passed) {
            true -> Text(
                "PASS (${result.durationMs}ms)",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium
            )
            false -> Text(
                "FAIL",
                color = MaterialTheme.colorScheme.error,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium
            )
            null -> CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
        }
    }
}

// ── Automated test runner ─────────────────────────────────────────────

private suspend fun runAutomatedTests(
    tau: TauSync,
    results: MutableList<TestResult>,
    log: (String) -> Unit
) {
    withContext(Dispatchers.Main) {
        results.add(TestResult("Message Exchange", null))
        results.add(TestResult("Binary Transfer", null))
    }

    val msgResult = runMessageExchangeTest(tau, log)
    withContext(Dispatchers.Main) { results[0] = msgResult }

    val binResult = runBinaryTransferTest(tau, log)
    withContext(Dispatchers.Main) { results[1] = binResult }
}

/**
 * Test 1: Connect on "test_msg", send a line, expect an echo back.
 *
 * Server protocol (server.py):
 * 1. Server opens channel "test_msg"
 * 2. Android sends "Hello from Android\n"
 * 3. Server reads and echoes back the same line
 * 4. Android verifies
 */
private suspend fun runMessageExchangeTest(
    tau: TauSync,
    log: (String) -> Unit
): TestResult {
    val start = System.currentTimeMillis()
    return try {
        withContext(Dispatchers.Main) { log("[Test 1] Message Exchange: opening channel 'test_msg'...") }
        val stream = withContext(Dispatchers.IO) { tau.connect("test_msg") }
        withContext(Dispatchers.Main) { log("[Test 1] Channel open, sending message...") }

        val sent = "Hello from Android"
        withContext(Dispatchers.IO) { stream.writeString(sent + "\n") }
        withContext(Dispatchers.Main) { log("[Test 1] Sent: $sent") }

        val reply = withContext(Dispatchers.IO) { stream.readLine() }
        withContext(Dispatchers.Main) { log("[Test 1] Received: $reply") }

        withContext(Dispatchers.IO) { stream.close() }

        val passed = reply == sent
        val elapsed = System.currentTimeMillis() - start
        if (!passed) {
            withContext(Dispatchers.Main) { log("[Test 1] FAIL: expected '$sent', got '$reply'") }
        } else {
            withContext(Dispatchers.Main) { log("[Test 1] PASS (${elapsed}ms)") }
        }
        TestResult("Message Exchange", passed, elapsed)
    } catch (e: Exception) {
        val elapsed = System.currentTimeMillis() - start
        withContext(Dispatchers.Main) { log("[Test 1] FAIL: ${e.message}") }
        TestResult("Message Exchange", false, elapsed)
    }
}

/**
 * Test 2: Connect on "test_bin", receive 25KB random data, echo it back,
 * then receive SHA-256 and verify.
 *
 * Server protocol (server.py):
 * 1. Server opens channel "test_bin"
 * 2. Server sends "25600\n" (data length)
 * 3. Server sends 25600 bytes of random data
 * 4. Android reads the data and echoes it back
 * 5. Server verifies and sends "PASS\n" or "FAIL\n"
 */
private suspend fun runBinaryTransferTest(
    tau: TauSync,
    log: (String) -> Unit
): TestResult {
    val start = System.currentTimeMillis()
    return try {
        withContext(Dispatchers.Main) { log("[Test 2] Binary Transfer: opening channel 'test_bin'...") }
        val stream = withContext(Dispatchers.IO) { tau.connect("test_bin") }
        withContext(Dispatchers.Main) { log("[Test 2] Channel open, reading data size...") }

        val sizeLine = withContext(Dispatchers.IO) { stream.readLine() }
            ?: throw Exception("EOF before size line")
        val dataSize = sizeLine.trim().toInt()
        withContext(Dispatchers.Main) { log("[Test 2] Expecting $dataSize bytes...") }

        val data = withContext(Dispatchers.IO) { stream.readExactly(dataSize) }
        withContext(Dispatchers.Main) { log("[Test 2] Received ${data.size} bytes, echoing back...") }

        val localSha = sha256Hex(data)
        withContext(Dispatchers.Main) { log("[Test 2] Local SHA-256: $localSha") }

        withContext(Dispatchers.IO) { stream.write(data) }
        withContext(Dispatchers.Main) { log("[Test 2] Echo sent, reading server verdict...") }

        val verdict = withContext(Dispatchers.IO) { stream.readLine() }
        withContext(Dispatchers.Main) { log("[Test 2] Server says: $verdict") }

        withContext(Dispatchers.IO) { stream.close() }

        val passed = verdict?.trim() == "PASS"
        val elapsed = System.currentTimeMillis() - start
        withContext(Dispatchers.Main) { log("[Test 2] ${if (passed) "PASS" else "FAIL"} (${elapsed}ms)") }
        TestResult("Binary Transfer", passed, elapsed)
    } catch (e: Exception) {
        val elapsed = System.currentTimeMillis() - start
        withContext(Dispatchers.Main) { log("[Test 2] FAIL: ${e.message}") }
        TestResult("Binary Transfer", false, elapsed)
    }
}

// ── Utilities ─────────────────────────────────────────────────────────

private fun sha256Hex(data: ByteArray): String {
    val digest = MessageDigest.getInstance("SHA-256").digest(data)
    return digest.joinToString("") { "%02x".format(it) }
}

private fun getLocalIpAddress(context: Context): String {
    return try {
        @Suppress("DEPRECATION")
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        val ipInt = wifiManager.connectionInfo.ipAddress
        @Suppress("DEPRECATION")
        if (ipInt == 0) "Disconnected" else Formatter.formatIpAddress(ipInt)
    } catch (_: Exception) {
        "Unknown"
    }
}
