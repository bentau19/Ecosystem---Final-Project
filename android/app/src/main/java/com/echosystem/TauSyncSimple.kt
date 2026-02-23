package com.echosystem

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.tausync.implementations.management.ConnectionManager
import com.tausync.implementations.transport.SocketTransport
import com.tausync.interfaces.IConnectionManager
import com.tausync.interfaces.ITransport
import com.tausync.models.TransferRequest
import java.net.ServerSocket
import java.nio.charset.StandardCharsets

/**
 * Simple TauSync example - sends/receives "hello world"
 */
class TauSyncSimple : AppCompatActivity() {
    private var connectionManager: IConnectionManager? = null
    private var transport: ITransport? = null
    private var serverThread: Thread? = null
    private var isServerRunning = false
    
    private lateinit var statusText: TextView
    private lateinit var receivedText: TextView
    private lateinit var sendButton: Button
    private lateinit var startButton: Button
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_simple)
        
        statusText = findViewById(R.id.statusText)
        receivedText = findViewById(R.id.receivedText)
        sendButton = findViewById(R.id.sendButton)
        startButton = findViewById(R.id.startButton)
        
        startButton.setOnClickListener {
            if (isServerRunning) {
                stopServer()
            } else {
                startServer()
            }
        }
        
        sendButton.setOnClickListener {
            sendHelloWorld()
        }
    }
    
    private fun startServer() {
        if (isServerRunning) return
        
        serverThread = Thread {
            try {
                val serverSocket = ServerSocket(8888)
                isServerRunning = true
                
                runOnUiThread {
                    statusText.text = "Server started. Waiting for connection..."
                    startButton.text = "Stop Server"
                }
                
                // Accept connection
                val clientSocket = serverSocket.accept()
                serverSocket.close()
                
                runOnUiThread {
                    statusText.text = "Client connected!"
                }
                
                // Initialize TauSync
                initializeTauSync(clientSocket)
                
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Server error: ${e.message}"
                    isServerRunning = false
                    startButton.text = "Start Server"
                }
            }
        }
        serverThread?.start()
    }
    
    private fun stopServer() {
        isServerRunning = false
        serverThread?.interrupt()
        transport?.let {
            (it as? SocketTransport)?.disconnect()
        }
        runOnUiThread {
            statusText.text = "Server stopped"
            startButton.text = "Start Server"
        }
    }
    
    private fun initializeTauSync(clientSocket: java.net.Socket) {
        // Create socket transport
        transport = SocketTransport()
        (transport as SocketTransport).port = 8888
        
        // Create connection manager (no secure channel needed)
        connectionManager = ConnectionManager()
        connectionManager?.initialize(transport!!)
        
        // Set up listeners
        connectionManager?.setRequestReceivedListener { req ->
            runOnUiThread {
                val message = String(req.payload, StandardCharsets.UTF_8)
                receivedText.text = "Received: $message"
                statusText.text = "Message received!"
            }
        }
        
        connectionManager?.setErrorOccurredListener { ex ->
            runOnUiThread {
                statusText.text = "Error: ${ex.message}"
            }
        }
        
        runOnUiThread {
            statusText.text = "TauSync ready!"
        }
    }
    
    private fun sendHelloWorld() {
        Thread {
            try {
                if (transport == null || !transport!!.isConnected) {
                    runOnUiThread {
                        statusText.text = "Not connected. Please start server first."
                    }
                    return@Thread
                }
                
                val request = TransferRequest()
                request.payload = "hello world".toByteArray(StandardCharsets.UTF_8)
                request.priority = 0
                request.isCompressed = false
                request.cryptoIV = ByteArray(0) // Empty - no encryption
                
                connectionManager?.smartSend(request)
                
                runOnUiThread {
                    statusText.text = "Sent: hello world"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Send error: ${e.message}"
                }
            }
        }.start()
    }
    
    override fun onDestroy() {
        super.onDestroy()
        stopServer()
    }
}
