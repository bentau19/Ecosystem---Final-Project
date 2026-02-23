package com.echosystem

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.tausync.implementations.management.ConnectionManager
import com.tausync.implementations.security.SecureChannel
import com.tausync.implementations.transport.SocketTransport
import com.tausync.interfaces.IConnectionManager
import com.tausync.interfaces.ISecureChannel
import com.tausync.interfaces.ITransport
import com.tausync.models.TransferRequest
import java.nio.charset.StandardCharsets
import java.security.SecureRandom

class TauSyncActivity : AppCompatActivity() {
    private lateinit var connectionManager: IConnectionManager
    private lateinit var transport: ITransport
    private lateinit var secureChannel: ISecureChannel
    
    private lateinit var statusText: TextView
    private lateinit var messageInput: EditText
    private lateinit var sendButton: Button
    private lateinit var receivedText: TextView
    private lateinit var connectButton: Button
    
    private var sharedKey: ByteArray? = null
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_tausync)
        
        // Initialize UI
        statusText = findViewById(R.id.statusText)
        messageInput = findViewById(R.id.messageInput)
        sendButton = findViewById(R.id.sendButton)
        receivedText = findViewById(R.id.receivedText)
        connectButton = findViewById(R.id.connectButton)
        
        // Generate shared key (in production, exchange securely)
        sharedKey = ByteArray(32)
        SecureRandom().nextBytes(sharedKey!!)
        
        // Initialize TauSync components
        initializeTauSync()
        
        // Setup UI handlers
        connectButton.setOnClickListener {
            connectToWindows()
        }
        
        sendButton.setOnClickListener {
            sendMessage()
        }
    }
    
    private fun initializeTauSync() {
        // Create secure channel
        secureChannel = SecureChannel()
        secureChannel.initialize(sharedKey!!)
        
        // Create socket transport
        transport = SocketTransport()
        (transport as SocketTransport).port = 8888
        
        // Create connection manager
        connectionManager = ConnectionManager()
        connectionManager.initialize(transport, secureChannel)
        
        // Set up listeners
        connectionManager.setRequestReceivedListener { req ->
            runOnUiThread {
                val message = String(req.payload, StandardCharsets.UTF_8)
                receivedText.append("Received: $message\n")
            }
        }
        
        connectionManager.setErrorOccurredListener { ex ->
            runOnUiThread {
                statusText.text = "Error: ${ex.message}"
            }
        }
        
        updateStatus("TauSync initialized. Click Connect to start.")
    }
    
    private fun connectToWindows() {
        // For this example, we'll act as a server (waiting for connection)
        // In a real app, you might want to get the Windows IP from user input
        Thread {
            try {
                // Note: This is a simplified example. In production, you'd want to:
                // 1. Get Windows IP from user input or discovery
                // 2. Handle connection errors properly
                // 3. Implement server socket to accept connections
                
                updateStatus("Connecting...")
                // For now, we'll wait for connection in a separate server thread
                // The actual connection will be initiated by Windows client
                updateStatus("Waiting for connection from Windows...")
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Connection error: ${e.message}"
                }
            }
        }.start()
    }
    
    private fun sendMessage() {
        val message = messageInput.text.toString()
        if (message.isEmpty()) {
            return
        }
        
        Thread {
            try {
                if (!transport.isConnected) {
                    runOnUiThread {
                        statusText.text = "Not connected. Please connect first."
                    }
                    return@Thread
                }
                
                val request = TransferRequest()
                request.payload = message.toByteArray(StandardCharsets.UTF_8)
                request.priority = 0
                request.isCompressed = false
                request.cryptoIV = ByteArray(0) // Will be generated automatically
                
                connectionManager.smartSend(request)
                
                runOnUiThread {
                    messageInput.text.clear()
                    statusText.text = "Message sent: $message"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Send error: ${e.message}"
                }
            }
        }.start()
    }
    
    private fun updateStatus(message: String) {
        runOnUiThread {
            statusText.text = message
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        if (::transport.isInitialized) {
            (transport as? SocketTransport)?.disconnect()
        }
    }
}
