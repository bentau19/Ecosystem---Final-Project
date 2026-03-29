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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TestTauSyncActivity extends AppCompatActivity {

    private TauSync tauSync;
    private TauSyncStream activeStream;
    private final ExecutorService backgroundExecutor = Executors.newSingleThreadExecutor();

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
            runMessageExchangeTest();
            runBinaryTransferTest();
            runOnUiThread(() -> {
                runAllTestsButton.setEnabled(true);
                runAllTestsButton.setText("Run All Tests");
            });
        });
    }

    private void runMessageExchangeTest() {
        long startTime = System.currentTimeMillis();
        runOnUiThread(() -> appendLog("[Test 1] Message Exchange: opening channel 'test_msg'..."));

        try {
            TauSyncStream stream = tauSync.connect("test_msg");
            runOnUiThread(() -> appendLog("[Test 1] Channel open, sending message..."));

            String sentMessage = "Hello from Android";
            stream.writeString(sentMessage + "\n");
            runOnUiThread(() -> appendLog("[Test 1] Sent: " + sentMessage));

            String reply = stream.readLine();
            runOnUiThread(() -> appendLog("[Test 1] Received: " + reply));

            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = sentMessage.equals(reply);
            String verdict = passed ? "PASS" : "FAIL";
            runOnUiThread(() -> appendLog("[Test 1] " + verdict + " (" + elapsed + "ms)"));
        } catch (Exception exception) {
            long elapsed = System.currentTimeMillis() - startTime;
            runOnUiThread(() -> appendLog("[Test 1] FAIL: " + exception.getMessage() + " (" + elapsed + "ms)"));
        }
    }

    private void runBinaryTransferTest() {
        long startTime = System.currentTimeMillis();
        runOnUiThread(() -> appendLog("[Test 2] Binary Transfer: opening channel 'test_bin'..."));

        try {
            TauSyncStream stream = tauSync.connect("test_bin");
            runOnUiThread(() -> appendLog("[Test 2] Channel open, reading data size..."));

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size line");
            int dataSize = Integer.parseInt(sizeLine.trim());
            runOnUiThread(() -> appendLog("[Test 2] Expecting " + dataSize + " bytes..."));

            byte[] data = stream.readExactly(dataSize);
            runOnUiThread(() -> appendLog("[Test 2] Received " + data.length + " bytes, echoing back..."));

            String localSha = computeSha256Hex(data);
            runOnUiThread(() -> appendLog("[Test 2] Local SHA-256: " + localSha));

            stream.write(data);
            runOnUiThread(() -> appendLog("[Test 2] Echo sent, reading server verdict..."));

            String verdict = stream.readLine();
            runOnUiThread(() -> appendLog("[Test 2] Server says: " + verdict));

            stream.close();

            long elapsed = System.currentTimeMillis() - startTime;
            boolean passed = verdict != null && verdict.trim().equals("PASS");
            String result = passed ? "PASS" : "FAIL";
            runOnUiThread(() -> appendLog("[Test 2] " + result + " (" + elapsed + "ms)"));
        } catch (Exception exception) {
            long elapsed = System.currentTimeMillis() - startTime;
            runOnUiThread(() -> appendLog("[Test 2] FAIL: " + exception.getMessage() + " (" + elapsed + "ms)"));
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
