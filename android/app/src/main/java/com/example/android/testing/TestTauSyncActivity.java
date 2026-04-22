package com.example.android.testing;

import android.content.Context;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.text.format.Formatter;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.example.tausync_lib.implementations.management.TauSyncStream;
import com.example.tausync_lib.sdk.TauSync;

import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class TestTauSyncActivity extends AppCompatActivity {

    private TauSync tauSync;
    private TauSyncStream activeStream;
    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();

    private EditText ipAddressInput;
    private EditText meetingWordInput;
    private EditText messageInput;
    private Button connectButton;
    private Button openChannelButton;
    private Button sendButton;
    private Button readLineButton;
    private Button runAllTestsButton;
    private TextView statusLabel;
    private TextView receivedLabel;
    private TextView logView;
    private ScrollView logScrollView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildLayout());
        disableStreamControls();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        backgroundExecutor.shutdownNow();
        closeStreamQuietly();
        disposeTauSyncQuietly();
    }

    // ── Layout ───────────────────────────────────────────────────────────

    private View buildLayout() {
        ScrollView root = new ScrollView(this);
        LinearLayout column = newVerticalColumn(16);

        addHeader(column);
        addConnectionSection(column);
        addManualTestSection(column);
        addAutomatedTestSection(column);
        addLogSection(column);

        root.addView(column);
        return root;
    }

    private void addHeader(LinearLayout parent) {
        TextView title = new TextView(this);
        title.setText("TauSync Test");
        title.setTextSize(24);

        TextView localIp = new TextView(this);
        localIp.setText("Local IP: " + resolveLocalIpAddress());
        localIp.setTextSize(12);

        parent.addView(title);
        parent.addView(localIp);
    }

    private void addConnectionSection(LinearLayout parent) {
        TextView sectionTitle = newSectionTitle("Connection");
        parent.addView(sectionTitle);

        ipAddressInput = newEditText("Server IP", "192.168.1.76");
        parent.addView(ipAddressInput);

        connectButton = new Button(this);
        connectButton.setText("Connect");
        connectButton.setOnClickListener(v -> onConnectButtonClicked());
        parent.addView(connectButton);

        statusLabel = new TextView(this);
        statusLabel.setText("Status: Disconnected");
        parent.addView(statusLabel);
    }

    private void addManualTestSection(LinearLayout parent) {
        TextView sectionTitle = newSectionTitle("Manual Test");
        parent.addView(sectionTitle);

        meetingWordInput = newEditText("Meeting Word", "main");
        parent.addView(meetingWordInput);

        openChannelButton = new Button(this);
        openChannelButton.setText("Open Channel");
        openChannelButton.setOnClickListener(v -> onOpenChannelButtonClicked());
        parent.addView(openChannelButton);

        messageInput = newEditText("Message", "Hello from Android!");
        parent.addView(messageInput);

        LinearLayout buttonRow = newHorizontalRow();

        sendButton = new Button(this);
        sendButton.setText("Send");
        sendButton.setOnClickListener(v -> onSendButtonClicked());
        buttonRow.addView(sendButton, newRowParams());

        readLineButton = new Button(this);
        readLineButton.setText("Read Line");
        readLineButton.setOnClickListener(v -> onReadLineButtonClicked());
        buttonRow.addView(readLineButton, newRowParams());

        parent.addView(buttonRow);

        receivedLabel = new TextView(this);
        parent.addView(receivedLabel);
    }

    private void addAutomatedTestSection(LinearLayout parent) {
        TextView sectionTitle = newSectionTitle("Automated Tests");
        parent.addView(sectionTitle);

        runAllTestsButton = new Button(this);
        runAllTestsButton.setText("Run All Tests");
        runAllTestsButton.setOnClickListener(v -> onRunAllTestsButtonClicked());
        parent.addView(runAllTestsButton);
    }

    private void addLogSection(LinearLayout parent) {
        TextView sectionTitle = newSectionTitle("Log");
        parent.addView(sectionTitle);

        logScrollView = new ScrollView(this);
        logScrollView.setMinimumHeight(300);

        logView = new TextView(this);
        logView.setTextSize(11);
        logView.setTypeface(android.graphics.Typeface.MONOSPACE);
        logScrollView.addView(logView);

        parent.addView(logScrollView);
    }

    // ── Connection actions ────────────────────────────────────────────────

    private void onConnectButtonClicked() {
        if (tauSync != null) {
            disconnect();
        } else {
            connectToServer(ipAddressInput.getText().toString().trim());
        }
    }

    private void connectToServer(String serverIp) {
        updateStatus("Connecting...");
        appendLog("Connecting to " + serverIp + "...");
        setConnectingState();

        backgroundExecutor.execute(() -> {
            try {
                TauSync newTauSync = new TauSync();
                newTauSync.connectTo(serverIp);
                runOnUiThread(() -> {
                    tauSync = newTauSync;
                    updateStatus("Connected to " + serverIp);
                    appendLog("Connected!");
                    setConnectedState();
                });
            } catch (Exception exception) {
                String rootCauseMessage = extractRootCauseMessage(exception);
                runOnUiThread(() -> {
                    updateStatus("Failed: " + rootCauseMessage);
                    appendLog("Connection failed: " + rootCauseMessage);
                    setDisconnectedState();
                });
            }
        });
    }

    private void disconnect() {
        backgroundExecutor.execute(() -> {
            closeStreamQuietly();
            disposeTauSyncQuietly();
            runOnUiThread(() -> {
                tauSync = null;
                activeStream = null;
                updateStatus("Disconnected");
                appendLog("Disconnected");
                setDisconnectedState();
            });
        });
    }

    // ── Channel actions ──────────────────────────────────────────────────

    private void onOpenChannelButtonClicked() {
        if (activeStream != null) {
            closeChannel();
        } else {
            openChannel(meetingWordInput.getText().toString().trim());
        }
    }

    private void openChannel(String meetingWord) {
        if (tauSync == null) return;
        appendLog("Opening channel \"" + meetingWord + "\"...");

        backgroundExecutor.execute(() -> {
            try {
                TauSyncStream stream = tauSync.connect(meetingWord);
                runOnUiThread(() -> {
                    activeStream = stream;
                    appendLog("Channel \"" + meetingWord + "\" opened (ID=" + stream.getLocalId() + ")");
                    enableStreamControls();
                });
            } catch (Exception exception) {
                String rootCauseMessage = extractRootCauseMessage(exception);
                runOnUiThread(() -> appendLog("Open channel failed: " + rootCauseMessage));
            }
        });
    }

    private void closeChannel() {
        backgroundExecutor.execute(() -> {
            closeStreamQuietly();
            runOnUiThread(() -> {
                activeStream = null;
                appendLog("Channel closed");
                disableStreamControls();
            });
        });
    }

    // ── Message actions ──────────────────────────────────────────────────

    private void onSendButtonClicked() {
        if (activeStream == null) return;
        String message = messageInput.getText().toString();
        appendLog("Sending: " + message);

        backgroundExecutor.execute(() -> {
            try {
                activeStream.writeString(message + "\n");
                runOnUiThread(() -> appendLog("Sent: " + message));
            } catch (Exception exception) {
                runOnUiThread(() -> appendLog("Send error: " + exception.getMessage()));
            }
        });
    }

    private void onReadLineButtonClicked() {
        if (activeStream == null) return;

        backgroundExecutor.execute(() -> {
            try {
                String line = activeStream.readLine();
                String displayText = (line != null) ? line : "<EOF>";
                runOnUiThread(() -> {
                    receivedLabel.setText("Received: " + displayText);
                    appendLog("Received: " + displayText);
                });
            } catch (Exception exception) {
                runOnUiThread(() -> appendLog("Read error: " + exception.getMessage()));
            }
        });
    }

    // ── Automated tests ──────────────────────────────────────────────────

    private void onRunAllTestsButtonClicked() {
        if (tauSync == null) return;
        runAllTestsButton.setEnabled(false);
        runAllTestsButton.setText("Running...");

        backgroundExecutor.execute(() -> {
            runMessageEchoTest();
            runBinaryRoundTripTest(25_600, "test_bin", "2");
            runEmptyMessageTest();
            runUnicodeRoundTripTest();
            runBinaryRoundTripTest(1_048_576, "test_large_bin", "5");
            runRapidBurstTest();
            runConcurrentChannelsTest();
            runStreamCloseTest();
            runOnUiThread(() -> {
                runAllTestsButton.setEnabled(true);
                runAllTestsButton.setText("Run All Tests");
            });
        });
    }

    // ── Test 1: Message echo ─────────────────────────────────────────────

    private void runMessageEchoTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 1] Message Echo: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_msg");
            String sentMessage = "Hello from Android";

            stream.writeString(sentMessage + "\n");
            String reply = stream.readLine();
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = sentMessage.equals(reply);
            appendLog("[Test 1] " + verdict(passed) + " (" + elapsed + "ms)"
                    + (passed ? "" : "  expected=" + sentMessage + " got=" + reply));
        } catch (Exception exception) {
            appendLog("[Test 1] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── Test 2 / 5: Binary round-trip (parameterized) ────────────────────

    private void runBinaryRoundTripTest(int expectedSize, String channelName, String testNumber) {
        long startTime = System.currentTimeMillis();
        appendLog("[Test " + testNumber + "] Binary (" + formatByteSize(expectedSize)
                + "): opening channel '" + channelName + "'...");

        try {
            TauSyncStream stream = tauSync.connect(channelName);

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size header");
            int dataSize = Integer.parseInt(sizeLine.trim());

            byte[] data = stream.readExactly(dataSize);
            String localSha = computeSha256Hex(data);
            appendLog("[Test " + testNumber + "] Received " + data.length
                    + " bytes, SHA=" + localSha.substring(0, 16) + "...");

            stream.write(data);

            String serverVerdict = stream.readLine();
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            appendLog("[Test " + testNumber + "] " + verdict(passed) + " (" + elapsed + "ms)");
        } catch (Exception exception) {
            appendLog("[Test " + testNumber + "] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── Test 3: Empty message ────────────────────────────────────────────

    private void runEmptyMessageTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 3] Empty Message: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_empty_msg");

            stream.writeString("\n");
            String reply = stream.readLine();
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = "".equals(reply);
            appendLog("[Test 3] " + verdict(passed) + " (" + elapsed + "ms)"
                    + (passed ? "" : "  expected='' got='" + reply + "'"));
        } catch (Exception exception) {
            appendLog("[Test 3] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── Test 4: Unicode round-trip ───────────────────────────────────────

    private void runUnicodeRoundTripTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 4] Unicode: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_unicode");

            String unicodePayload = stream.readLine();
            if (unicodePayload == null) throw new Exception("EOF before unicode payload");
            appendLog("[Test 4] Received: " + unicodePayload);

            stream.writeString(unicodePayload + "\n");

            String serverVerdict = stream.readLine();
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            appendLog("[Test 4] " + verdict(passed) + " (" + elapsed + "ms)");
        } catch (Exception exception) {
            appendLog("[Test 4] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── Test 6: Rapid burst ──────────────────────────────────────────────

    private void runRapidBurstTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 6] Rapid Burst: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_burst");

            String countLine = stream.readLine();
            if (countLine == null) throw new Exception("EOF before count header");
            int expectedCount = Integer.parseInt(countLine.trim());
            appendLog("[Test 6] Expecting " + expectedCount + " messages...");

            int receivedCount = 0;
            for (int i = 0; i < expectedCount; i++) {
                String line = stream.readLine();
                if (line == null) break;
                receivedCount++;
            }

            stream.writeString(receivedCount + "\n");

            String serverVerdict = stream.readLine();
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            appendLog("[Test 6] " + verdict(passed) + " (" + elapsed + "ms)"
                    + "  received=" + receivedCount + "/" + expectedCount);
        } catch (Exception exception) {
            appendLog("[Test 6] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── Test 7: Concurrent channels ──────────────────────────────────────

    private void runConcurrentChannelsTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 7] Concurrent Channels: opening A and B in parallel...");

        AtomicBoolean channelAPassed = new AtomicBoolean(false);
        AtomicBoolean channelBPassed = new AtomicBoolean(false);
        CountDownLatch bothDone = new CountDownLatch(2);

        backgroundExecutor.execute(() -> {
            channelAPassed.set(runSingleChannelEcho("test_concurrent_a", "7a", "concurrent_A"));
            bothDone.countDown();
        });
        backgroundExecutor.execute(() -> {
            channelBPassed.set(runSingleChannelEcho("test_concurrent_b", "7b", "concurrent_B"));
            bothDone.countDown();
        });

        try {
            bothDone.await(30, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {}

        long elapsed = System.currentTimeMillis() - startTime;
        boolean passed = channelAPassed.get() && channelBPassed.get();
        appendLog("[Test 7] " + verdict(passed) + " (" + elapsed + "ms)");
    }

    private boolean runSingleChannelEcho(String channelName, String label, String payload) {
        try {
            TauSyncStream stream = tauSync.connect(channelName);
            stream.writeString(payload + "\n");
            String reply = stream.readLine();
            stream.close();

            boolean passed = payload.equals(reply);
            appendLog("  [" + label + "] " + verdict(passed)
                    + (passed ? "" : "  expected=" + payload + " got=" + reply));
            return passed;
        } catch (Exception exception) {
            appendLog("  [" + label + "] FAIL: " + exception.getMessage());
            return false;
        }
    }

    // ── Test 8: Stream close / EOF detection ─────────────────────────────

    private void runStreamCloseTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 8] Stream Close: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_stream_close");

            byte[] data = stream.readAll();
            String content = new String(data, java.nio.charset.StandardCharsets.UTF_8);
            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = "CLOSE_TEST_DATA".equals(content);
            appendLog("[Test 8] " + verdict(passed) + " (" + elapsed + "ms)"
                    + (passed ? "  EOF detected correctly"
                              : "  expected='CLOSE_TEST_DATA' got='" + content + "'"));
        } catch (Exception exception) {
            appendLog("[Test 8] FAIL: " + exception.getMessage()
                    + " (" + elapsed(startTime) + "ms)");
        }
    }

    // ── UI state management ──────────────────────────────────────────────

    private void setConnectedState() {
        connectButton.setText("Disconnect");
        connectButton.setEnabled(true);
        ipAddressInput.setEnabled(false);
        openChannelButton.setEnabled(true);
    }

    private void setDisconnectedState() {
        connectButton.setText("Connect");
        connectButton.setEnabled(true);
        ipAddressInput.setEnabled(true);
        openChannelButton.setEnabled(false);
        disableStreamControls();
    }

    private void setConnectingState() {
        connectButton.setEnabled(false);
        ipAddressInput.setEnabled(false);
    }

    private void enableStreamControls() {
        openChannelButton.setText("Close Channel");
        meetingWordInput.setEnabled(false);
        sendButton.setEnabled(true);
        readLineButton.setEnabled(true);
        messageInput.setEnabled(true);
    }

    private void disableStreamControls() {
        openChannelButton.setText("Open Channel");
        meetingWordInput.setEnabled(true);
        sendButton.setEnabled(false);
        readLineButton.setEnabled(false);
        messageInput.setEnabled(false);
        receivedLabel.setText("");
    }

    private void updateStatus(String status) {
        statusLabel.setText("Status: " + status);
    }

    private void appendLog(String message) {
        String timestamp = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        String entry = "[" + timestamp + "] " + message + "\n";
        runOnUiThread(() -> {
            logView.append(entry);
            logScrollView.post(() -> logScrollView.fullScroll(View.FOCUS_DOWN));
        });
    }

    // ── Utilities ────────────────────────────────────────────────────────

    private String resolveLocalIpAddress() {
        try {
            WifiManager wifiManager = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            int ipInt = wifiManager.getConnectionInfo().getIpAddress();
            return (ipInt == 0) ? "Disconnected" : Formatter.formatIpAddress(ipInt);
        } catch (Exception exception) {
            return "Unknown";
        }
    }

    private static String computeSha256Hex(byte[] data) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder hexString = new StringBuilder();
            for (byte b : digest) {
                hexString.append(String.format("%02x", b));
            }
            return hexString.toString();
        } catch (Exception exception) {
            return "error";
        }
    }

    private static String verdict(boolean passed) {
        return passed ? "PASS" : "FAIL";
    }

    private static long elapsed(long startTime) {
        return System.currentTimeMillis() - startTime;
    }

    private static String formatByteSize(int bytes) {
        if (bytes >= 1_048_576) return (bytes / 1_048_576) + " MB";
        if (bytes >= 1_024) return (bytes / 1_024) + " KB";
        return bytes + " B";
    }

    private static String extractRootCauseMessage(Exception exception) {
        Throwable cause = exception;
        while (cause.getCause() != null) {
            cause = cause.getCause();
        }
        return cause.getClass().getSimpleName() + ": " + cause.getMessage();
    }

    private void closeStreamQuietly() {
        try {
            if (activeStream != null) activeStream.close();
        } catch (Exception ignored) {}
    }

    private void disposeTauSyncQuietly() {
        try {
            if (tauSync != null) tauSync.dispose();
        } catch (Exception ignored) {}
    }

    // ── View factory helpers ─────────────────────────────────────────────

    private LinearLayout newVerticalColumn(int paddingDp) {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int paddingPixels = dpToPixels(paddingDp);
        column.setPadding(paddingPixels, paddingPixels, paddingPixels, paddingPixels);
        return column;
    }

    private LinearLayout newHorizontalRow() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        return row;
    }

    private EditText newEditText(String hint, String defaultValue) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setText(defaultValue);
        editText.setSingleLine(true);
        return editText;
    }

    private TextView newSectionTitle(String title) {
        TextView textView = new TextView(this);
        textView.setText(title);
        textView.setTextSize(18);
        textView.setPadding(0, dpToPixels(12), 0, dpToPixels(4));
        return textView;
    }

    private LinearLayout.LayoutParams newRowParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.weight = 1;
        params.setMargins(dpToPixels(4), 0, dpToPixels(4), 0);
        return params;
    }

    private int dpToPixels(int dp) {
        return (int) (dp * getResources().getDisplayMetrics().density);
    }
}
