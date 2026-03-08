package com.example.android

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.net.wifi.WifiManager
import android.os.Bundle
import android.text.format.Formatter
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.android.ui.theme.AndroidTheme
import com.example.tausync_lib.TauSyncJavaEngine
import com.example.tausync_lib.implementations.management.ConnectionManager
import com.tausync.interfaces.IConnectionManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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
                    ClipboardReceiverScreen(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

@Composable
fun ClipboardReceiverScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var pcIp by remember { mutableStateOf("192.168.1.76") }
    var connectionManager by remember { mutableStateOf<ConnectionManager?>(null) }
    var connectionStatus by remember { mutableStateOf("לא מחובר") }
    var receivedClipboard by remember { mutableStateOf<String?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val javaEngine = remember { TauSyncJavaEngine() }
    var localIp by remember { mutableStateOf(getLocalIpAddress(context)) }

    LaunchedEffect(connectionManager) {
        val manager = connectionManager ?: return@LaunchedEffect
        manager.setOnClipboardReceivedListener(IConnectionManager.ClipboardReceivedListener { text ->
            (context as? Activity)?.runOnUiThread {
                receivedClipboard = text
                errorMessage = null
            }
        })
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Icon(
            imageVector = Icons.Default.Info,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(64.dp)
        )

        Text(
            text = "TauSync – קבלת Clipboard מהמחשב",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )

        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.elevatedCardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    "כתובת IP של המחשב (שם רץ benTest.py)",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.secondary
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = pcIp,
                    onValueChange = { pcIp = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    placeholder = { Text("192.168.1.76") }
                )
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = {
                        if (connectionManager != null) {
                            connectionManager?.close()
                            connectionManager = null
                            connectionStatus = "לא מחובר"
                            receivedClipboard = null
                            return@Button
                        }
                        connectionStatus = "מתחבר..."
                        errorMessage = null
                        scope.launch {
                            try {
                                val manager = ConnectionManager()
                                withContext(Dispatchers.IO) {
                                    manager.connect(pcIp.trim()).get()
                                }
                                connectionManager = manager
                                connectionStatus = "מחובר ל־$pcIp"
                            } catch (e: Exception) {
                                connectionStatus = "לא מחובר"
                                errorMessage = "שגיאה: ${e.message}"
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(
                        if (connectionManager != null) "נתק" else "התחבר למחשב"
                    )
                }
            }
        }

        Text(
            text = connectionStatus,
            style = MaterialTheme.typography.titleMedium,
            color = if (connectionManager != null)
                MaterialTheme.colorScheme.primary
            else
                MaterialTheme.colorScheme.onSurfaceVariant
        )

        errorMessage?.let { msg ->
            Text(
                text = msg,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error
            )
        }

        if (receivedClipboard != null) {
            ElevatedCard(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.elevatedCardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        "Clipboard שהתקבל מהמחשב",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = receivedClipboard ?: "",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = {
                            receivedClipboard?.let { copyToClipboard(context, it) }
                        },
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("העתק ללוח")
                    }
                }
            }
        } else if (connectionManager != null) {
            Text(
                "מחכה ל־clipboard מהמחשב... (הרץ benTest.py על ה־PC)",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.secondary
            )
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.elevatedCardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "כתובת IP של המכשיר (להקלדה ב־benTest אם צריך)",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.secondary
                )
                Text(
                    text = localIp,
                    style = MaterialTheme.typography.displaySmall.copy(
                        fontWeight = FontWeight.ExtraBold,
                        letterSpacing = 1.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { copyToClipboard(context, localIp) },
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("העתק IP")
                    }
                    OutlinedButton(
                        onClick = { localIp = getLocalIpAddress(context) },
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("רענן")
                    }
                }
            }
        }

        Text(
            text = javaEngine.statusMessage,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline
        )
    }
}

fun getLocalIpAddress(context: Context): String {
    return try {
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val ipInt = wifiManager.connectionInfo.ipAddress
        if (ipInt == 0) "Disconnected" else Formatter.formatIpAddress(ipInt)
    } catch (e: Exception) {
        "Unknown"
    }
}

fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    val clip = ClipData.newPlainText("TauSync", text)
    clipboard.setPrimaryClip(clip)
    Toast.makeText(context, "הועתק ללוח!", Toast.LENGTH_SHORT).show()
}
