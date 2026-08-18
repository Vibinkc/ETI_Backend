"""Widget.js endpoint - serves the embeddable bot widget as a JavaScript file."""

import os

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.get("/widget.js")
async def get_widget_js() -> Response:
    """
    Serve the embeddable bot widget as a JavaScript file.

    This allows websites to embed with just: <script src=".../widget.js"></script>
    """
    api_url = os.getenv("API_URL", "http://localhost:8000")

    widget_js = f"""
(function() {{
    // ETI Bot Widget
    const API_URL = '{api_url}/api/bot';
    
    // Generate session ID
    function getSessionId() {{
        let sessionId = localStorage.getItem('eti_session_id');
        if (!sessionId) {{
            sessionId = 'sess_' + Math.random().toString(36).substr(2, 16);
            localStorage.setItem('eti_session_id', sessionId);
        }}
        return sessionId;
    }}
    
    // Format markdown text to HTML
    function formatMessage(text) {{
        if (!text) return '';
        
        // Escape HTML first to prevent XSS
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Convert **bold** to <strong>
        html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
        
        // Split by lines to handle bullet points and lists
        const lines = html.split('\\n');
        let formattedLines = [];
        let inList = false;
        let listType = '';
        
        for (let i = 0; i < lines.length; i++) {{
            const line = lines[i].trim();
            
            // Check for bullet points (• or - or *)
            if (line.match(/^[•\\-\\*]\\s/)) {{
                if (!inList || listType !== 'ul') {{
                    if (inList && listType === 'ol') {{
                        formattedLines.push('</ol>');
                    }}
                    formattedLines.push('<ul style="margin: 8px 0; padding-left: 20px; list-style-type: disc;">');
                    inList = true;
                    listType = 'ul';
                }}
                // Remove bullet and format
                const content = line.replace(/^[•\\-\\*]\\s*/, '');
                formattedLines.push(`<li style="margin: 4px 0;">${{content}}</li>`);
            }}
            // Check for numbered lists
            else if (line.match(/^\\d+[\\.\\)]\\s/)) {{
                if (!inList || listType !== 'ol') {{
                    if (inList && listType === 'ul') {{
                        formattedLines.push('</ul>');
                    }}
                    formattedLines.push('<ol style="margin: 8px 0; padding-left: 20px;">');
                    inList = true;
                    listType = 'ol';
                }}
                const content = line.replace(/^\\d+[\\.\\)]\\s*/, '');
                formattedLines.push(`<li style="margin: 4px 0;">${{content}}</li>`);
            }}
            else {{
                // Close list if we were in one
                if (inList) {{
                    formattedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
                    inList = false;
                    listType = '';
                }}
                
                // Regular paragraph
                if (line) {{
                    formattedLines.push(`<p style="margin: 8px 0;">${{line}}</p>`);
                }} else {{
                    formattedLines.push('<br>');
                }}
            }}
        }}
        
        // Close list if still open
        if (inList) {{
            formattedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
        }}
        
        return formattedLines.join('');
    }}
    
    // Create widget HTML
    function createWidget() {{
        const widget = document.createElement('div');
        widget.id = 'eti-bot-widget';
        widget.innerHTML = `
            <div id="eti-widget-wrapper" style="position: fixed; bottom: 20px; right: 20px; z-index: 10000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div id="eti-bot-container" style="display: none; width: 320px; height: 500px; background: white; border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.12); flex-direction: column; position: relative; overflow: hidden; transition: all 0.3s ease;">
                    <!-- Header -->
                    <div style="background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button id="eti-back-btn" style="display: none; background: none; border: none; color: white; cursor: pointer; margin-right: 4px; transition: opacity 0.2s; flex-shrink: 0; padding: 4px;">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M19 12H5"></path>
                                    <path d="M12 19l-7-7 7-7"></path>
                                </svg>
                            </button>
                            <div style="width: 36px; height: 36px; border-radius: 50%; background: white; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                                <img src="{api_url}/static/ETI_logo.svg" alt="ETI Logo" style="width: 28px; height: 28px; object-fit: contain;" onerror="this.style.display='none';" />
                            </div>
                            <div>
                                <h3 id="eti-header-title" style="margin: 0; font-size: 14px; font-weight: 600; line-height: 1.2; color: #ffffff;">ETI Assistant</h3>
                                <p id="eti-header-status" style="margin: 2px 0 0 0; font-size: 11px; opacity: 0.95; color: #ffffff; display: flex; align-items: center; gap: 5px;">
                                    <span style="width: 6px; height: 6px; background: #3A621A; border-radius: 50%; display: inline-block; box-shadow: 0 0 3px rgba(58, 98, 26, 0.6);"></span>
                                    We are online!
                                </p>
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <button id="eti-end-chat-btn" style="display: none; background: rgba(3, 31, 74, 0.2); border: none; color: white; width: 28px; height: 28px; border-radius: 50%; cursor: pointer; font-size: 16px; line-height: 1; transition: all 0.2s; padding: 0; display: flex; align-items: center; justify-content: center;" title="End Chat">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
                                    <line x1="12" y1="2" x2="12" y2="12"></line>
                                </svg>
                            </button>
                        <button id="eti-close-btn" style="background: none; border: none; color: white; cursor: pointer; font-size: 24px; line-height: 1; transition: opacity 0.2s; padding: 4px; display: flex; align-items: center; justify-content: center;">×</button>
                        </div>
                    </div>
                    
                    <!-- Home View -->
                    <div id="eti-home-view" style="flex: 1; overflow: hidden; padding: 12px 14px; background: #EFF1ED; display: flex; flex-direction: column; gap: 12px; min-height: 0; align-items: center; justify-content: center;">
                        <div style="text-align: center; padding: 6px 0; width: 100%;">
                            <img src="{api_url}/static/eti-only-logo.svg" alt="ETI Logo" style="height: 36px; width: auto; margin: 0 auto 16px; display: block;" onerror="this.style.display='none';" />
                            <h3 style="margin: 0 0 4px 0; font-size: 16px; font-weight: 600; color: #031F4A;">Welcome to ETI Assistant</h3>
                            <p style="margin: 0; font-size: 12px; color: #373D20; line-height: 1.4;">Your AI-powered assistant is here to help</p>
                        </div>
                        
                        <div style="display: flex; flex-direction: column; gap: 6px; width: 100%; align-items: center;">
                            <div style="background: white; padding: 10px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); width: 100%; max-width: 100%;">
                                <div style="display: flex; align-items: center; gap: 10px; justify-content: center;">
                                    <div style="width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                            <circle cx="12" cy="12" r="10"></circle>
                                            <polyline points="12 6 12 12 16 14"></polyline>
                                        </svg>
                                    </div>
                                    <div style="flex: 1; min-width: 0; text-align: left;">
                                        <h4 style="margin: 0; font-size: 13px; font-weight: 600; color: #031F4A;">24/7 Support</h4>
                                        <p style="margin: 0; font-size: 11px; color: #373D20; line-height: 1.3;">Available round the clock</p>
                                    </div>
                                </div>
                            </div>
                            
                            <div style="background: white; padding: 10px; border-radius: 10px; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05); width: 100%; max-width: 100%;">
                                <div style="display: flex; align-items: center; gap: 10px; justify-content: center;">
                                    <div style="width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, #031F4A 0%, #70BB32 100%); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                                        </svg>
                                    </div>
                                    <div style="flex: 1; min-width: 0; text-align: left;">
                                        <h4 style="margin: 0; font-size: 13px; font-weight: 600; color: #031F4A;">Instant Responses</h4>
                                        <p style="margin: 0; font-size: 11px; color: #373D20; line-height: 1.3;">Get answers in seconds</p>
                                    </div>
                                </div>
                            </div>
                            
                            <div style="background: white; padding: 10px; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); width: 100%; max-width: 100%;">
                                <div style="display: flex; align-items: center; gap: 10px; justify-content: center;">
                                    <div style="width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, #031F4A 0%, #70BB32 100%); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                                            <path d="M2 17l10 5 10-5"></path>
                                            <path d="M2 12l10 5 10-5"></path>
                                        </svg>
                                    </div>
                                    <div style="flex: 1; min-width: 0; text-align: left;">
                                        <h4 style="margin: 0; font-size: 13px; font-weight: 600; color: #031F4A;">Smart AI Assistant</h4>
                                        <p style="margin: 0; font-size: 11px; color: #373D20; line-height: 1.3;">Intelligent and helpful responses</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Chat with us button -->
                        <button id="eti-chat-with-us-btn" style="margin-top: 8px; width: 100%; padding: 12px 16px; background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; border: none; border-radius: 12px; font-size: 14px; font-weight: 600; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; box-shadow: 0 2px 8px rgba(3, 31, 74, 0.3); display: flex; align-items: center; justify-content: center; gap: 10px;">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                            </svg>
                            <span>Chat with us</span>
                        </button>
                    </div>
                    
                    <!-- Conversation View -->
                    <div id="eti-conversation-view" style="flex: 1; overflow-y: auto; padding: 16px; background: #EFF1ED; display: none; flex-direction: column; gap: 12px; min-height: 0;">
                        <div id="eti-messages" style="display: flex; flex-direction: column; gap: 12px;">
                            <!-- Messages will be added dynamically -->
                                </div>
                    </div>
                    
                    <!-- Input Area (only shown in conversation view) -->
                    <div id="eti-input-area" style="border-top: 1px solid #EFF1ED; padding: 10px 12px; background: white; display: none;">
                        <div id="eti-chat-controls" style="position: relative;">
                            <div style="display: flex; align-items: center; gap: 6px; background: #EFF1ED; border-radius: 20px; padding: 3px 3px 3px 12px; border: 1px solid #EFF1ED;">
                                <input id="eti-input" type="text" placeholder="Enter your message..." style="flex: 1; border: none; background: transparent; padding: 8px 6px; font-size: 13px; outline: none; color: #031F4A;" />
                                <button id="eti-send-btn" style="background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; border: none; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; box-shadow: 0 2px 6px rgba(3, 31, 74, 0.3);" title="Send message">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                        <line x1="22" y1="2" x2="11" y2="13"></line>
                                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Conversations List View -->
                    <div id="eti-conversations-view" style="flex: 1; overflow-y: auto; padding: 12px; background: #EFF1ED; display: none; flex-direction: column; gap: 8px; min-height: 0;">
                        <div id="eti-conversations-list" style="display: flex; flex-direction: column; gap: 8px;">
                            <!-- Conversations will be loaded here -->
                        </div>
                        <div id="eti-no-conversations" style="text-align: center; padding: 40px 20px; color: #373D20; font-size: 13px;">
                            No conversations yet. Start chatting to see your conversations here.
                        </div>
                    </div>
                    
                    <!-- Bottom Tab Navigation -->
                    <div id="eti-bottom-tabs" style="border-top: 1px solid #EFF1ED; background: white; display: flex; padding: 0;">
                        <button id="eti-home-tab" style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 8px 6px; background: none; border: none; cursor: pointer; transition: background 0.2s;">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#031F4A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 3px;">
                                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                                <polyline points="9 22 9 12 15 12 15 22"></polyline>
                            </svg>
                            <span style="font-size: 11px; font-weight: 500; color: #031F4A;">Home</span>
                            <div style="width: 100%; height: 2px; background: #031F4A; margin-top: 3px; border-radius: 2px 2px 0 0;"></div>
                        </button>
                        <button id="eti-conversations-tab" style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 8px 6px; background: none; border: none; cursor: pointer; transition: background 0.2s;">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 3px;">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                            </svg>
                            <span style="font-size: 11px; font-weight: 500; color: #9ca3af;">Conversations</span>
                            <div style="width: 100%; height: 2px; background: transparent; margin-top: 3px;"></div>
                        </button>
                    </div>
                </div>
                <div style="position: relative;">
                    <button id="eti-toggle-btn" style="width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); border: none; color: white; cursor: pointer; box-shadow: 0 4px 16px rgba(3, 31, 74, 0.4); display: flex; align-items: center; justify-content: center; transition: transform 0.2s, box-shadow 0.2s;">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 8V4H8"></path>
                        <rect width="16" height="12" x="4" y="8" rx="2"></rect>
                        <path d="M2 14h2"></path>
                        <path d="M20 14h2"></path>
                        <path d="M15 13v2"></path>
                        <path d="M9 13v2"></path>
                    </svg>
                    </button>
                    <div id="eti-tooltip" style="position: absolute; top: 50%; right: 70px; transform: translateY(-50%); background: white; padding: 12px 16px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); min-width: 200px; display: none; z-index: 10001; animation: fadeIn 0.3s ease-in;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                            <p style="margin: 0; font-size: 13px; color: #212529; line-height: 1.4; font-weight: 500;">Hello! 👋<br/>How can we help you?</p>
                            <button id="eti-tooltip-close" style="background: none; border: none; color: #6c757d; cursor: pointer; font-size: 18px; line-height: 1; padding: 0; margin-left: 8px; flex-shrink: 0; transition: color 0.2s;" title="Close">×</button>
                        </div>
                        <div style="position: absolute; top: 50%; right: -8px; transform: translateY(-50%); width: 0; height: 0; border-top: 8px solid transparent; border-bottom: 8px solid transparent; border-left: 8px solid white;"></div>
                    </div>
                </div>
            </div>
            <style>
                /* Scoped reset: stop the host site's stylesheet from leaking into the widget.
                   Low specificity on purpose - every inline style in the widget still wins. */
                #eti-bot-widget, #eti-bot-widget * {{
                    box-sizing: border-box;
                }}
                #eti-bot-widget h1, #eti-bot-widget h2, #eti-bot-widget h3,
                #eti-bot-widget h4, #eti-bot-widget h5, #eti-bot-widget h6,
                #eti-bot-widget p, #eti-bot-widget span, #eti-bot-widget div,
                #eti-bot-widget ul, #eti-bot-widget ol, #eti-bot-widget li,
                #eti-bot-widget a, #eti-bot-widget button, #eti-bot-widget input {{
                    color: inherit;
                    font-family: inherit;
                    letter-spacing: normal;
                    text-transform: none;
                    text-shadow: none;
                    text-decoration: none;
                }}
                #eti-bot-widget h1, #eti-bot-widget h2, #eti-bot-widget h3,
                #eti-bot-widget h4, #eti-bot-widget h5, #eti-bot-widget h6,
                #eti-bot-widget p {{
                    margin: 0;
                    padding: 0;
                }}
                #eti-bot-widget button, #eti-bot-widget input {{
                    background: none;
                    border: none;
                    margin: 0;
                    padding: 0;
                    box-shadow: none;
                    min-width: 0;
                    min-height: 0;
                    width: auto;
                    height: auto;
                    text-align: inherit;
                }}
                #eti-bot-widget img {{
                    max-width: none;
                    border: none;
                    border-radius: 0;
                    box-shadow: none;
                }}
                /* Header sits on a dark gradient and must stay white even if the
                   host theme colours headings with !important. */
                #eti-bot-widget #eti-header-title,
                #eti-bot-widget #eti-header-status {{
                    color: #ffffff !important;
                }}
                @keyframes fadeIn {{
                    from {{
                        opacity: 0;
                        transform: translateY(10px);
                    }}
                    to {{
                        opacity: 1;
                        transform: translateY(0);
                    }}
                }}
                @keyframes typing-dot {{
                    0%, 60%, 100% {{
                        transform: translateY(0);
                        opacity: 0.7;
                    }}
                    30% {{
                        transform: translateY(-10px);
                        opacity: 1;
                    }}
                }}
                @media (max-width: 480px) {{
                    #eti-widget-wrapper {{
                        bottom: 0 !important;
                        right: 0 !important;
                        width: 100% !important;
                        height: 100% !important;
                        pointer-events: none;
                    }}
                    #eti-bot-container {{
                        width: 100% !important;
                        height: 100% !important;
                        bottom: 0 !important;
                        right: 0 !important;
                        border-radius: 0 !important;
                        pointer-events: auto;
                    }}
                    #eti-toggle-btn {{
                        position: fixed !important;
                        bottom: 20px !important;
                        right: 20px !important;
                        pointer-events: auto !important;
                        z-index: 10001 !important;
                    }}
                    #eti-tooltip {{
                        position: fixed !important;
                        bottom: 25px !important;
                        right: 80px !important;
                        top: auto !important;
                        transform: none !important;
                        z-index: 10001 !important;
                    }}
                    #eti-tooltip div:last-child {{
                        display: none !important;
                    }}
                }}
            </style>
        `;
        document.body.appendChild(widget);
        return widget;
    }}
    
    // Initialize widget
    if (!document.getElementById('eti-bot-widget')) {{
        const widget = createWidget();
        const container = document.getElementById('eti-bot-container');
        const toggleBtn = document.getElementById('eti-toggle-btn');
        const closeBtn = document.getElementById('eti-close-btn');
        const sendBtn = document.getElementById('eti-send-btn');
        const input = document.getElementById('eti-input');
        const homeView = document.getElementById('eti-home-view');
        const conversationView = document.getElementById('eti-conversation-view');
        const messagesDiv = document.getElementById('eti-messages');
        const inputArea = document.getElementById('eti-input-area');
        const chatControls = document.getElementById('eti-chat-controls');
        const homeTab = document.getElementById('eti-home-tab');
        const conversationsTab = document.getElementById('eti-conversations-tab');
        const bottomTabs = document.getElementById('eti-bottom-tabs');
        const backBtn = document.getElementById('eti-back-btn');
        const tooltip = document.getElementById('eti-tooltip');
        const tooltipClose = document.getElementById('eti-tooltip-close');
        const chatWithUsBtn = document.getElementById('eti-chat-with-us-btn');
        const consultationBtn = document.getElementById('eti-consultation-btn');
        const faqsBtn = document.getElementById('eti-faqs-btn');
        const endChatBtn = document.getElementById('eti-end-chat-btn');
        const conversationsView = document.getElementById('eti-conversations-view');
        const conversationsList = document.getElementById('eti-conversations-list');
        const noConversations = document.getElementById('eti-no-conversations');
        
        const sessionId = getSessionId();
        const websiteUrl = window.location.href;
        
        let conversationStarted = false;
        let currentConversationId = null;
        // Track messages in memory for accurate saving (preserves full content)
        let messageHistory = [];
        
        // Check if we're on the widget page
        const isWidgetPage = window.location.pathname.includes('/widget');
        
        // Show tooltip when toggle button is visible
        function showTooltip() {{
            if (tooltip && toggleBtn.style.display !== 'none') {{
                // Check if tooltip was previously dismissed
                const tooltipDismissed = localStorage.getItem('eti_tooltip_dismissed');
                if (!tooltipDismissed) {{
                    tooltip.style.display = 'block';
                }}
            }}
        }}
        
        // Hide tooltip
        function hideTooltip() {{
            if (tooltip) {{
                tooltip.style.display = 'none';
            }}
        }}
        
        // Dismiss tooltip permanently
        if (tooltipClose) {{
            tooltipClose.addEventListener('click', () => {{
                hideTooltip();
                localStorage.setItem('eti_tooltip_dismissed', 'true');
            }});
        }}
        
        // Show tooltip when toggle button is visible
        setTimeout(() => {{
            showTooltip();
        }}, 1000);
        
        // Auto-open widget after 4 seconds on widget page
        if (isWidgetPage) {{
            setTimeout(() => {{
                if (container && toggleBtn) {{
                    container.style.display = 'flex';
                    toggleBtn.style.display = 'none';
                    hideTooltip(); // Hide tooltip when widget auto-opens
                    showHomeView();
                }}
            }}, 4000);
        }}
        
        // Function to show welcome message when starting conversation
        function showWelcomeMessage() {{
            if (messagesDiv.children.length === 0) {{
                const welcomeDiv = document.createElement('div');
                welcomeDiv.style.cssText = 'background: white; padding: 12px; border-radius: 8px; max-width: 85%; box-shadow: 0 1px 3px rgba(0,0,0,0.1); align-self: flex-start;';
                const now = new Date();
                const timeStr = now.toLocaleTimeString('en-US', {{ hour: '2-digit', minute: '2-digit' }});
                const welcomeText = '✨ <strong>Welcome to ETI!</strong> ✨<br/>How can we assist you today? 🤖<br/>We are here to help with any inquiries or support you need. Let us know how we can make your experience better! 😊✨';
                welcomeDiv.innerHTML = `
                    <img src="https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400&h=200&fit=crop&q=80" alt="AI Assistant Welcome" style="width: 100%; max-width: 280px; height: auto; border-radius: 8px; margin-bottom: 12px; object-fit: cover;" onerror="this.src='https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400&h=200&fit=crop&q=80';" />
                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #374151; line-height: 1.5;">${{welcomeText}}</p>
                    <p style="margin: 8px 0 0 0; font-size: 12px; color: #6b7280; text-align: right;">${{timeStr}}</p>
                `;
                messagesDiv.appendChild(welcomeDiv);
                
                // Scroll to show the welcome message
                setTimeout(() => {{
                    conversationView.scrollTop = conversationView.scrollHeight;
                }}, 100);
                
                // Clear any previous conversation ID
                currentConversationId = null;
                // Clear message history - will be initialized when user sends message
                messageHistory = [];
                
                // Directly enable FAQs (no buttons needed)
                if (inputArea) inputArea.style.display = 'block';
                if (endChatBtn) endChatBtn.style.display = 'flex';
            }}
        }}
        
        // Function to save conversation state (ongoing) - uses messageHistory for accurate content
        // CRITICAL: This should ONLY be called for welcome messages (initial save).
        // Bot API saves all user/assistant message pairs using $push.
        // This function should NOT be called after bot API has saved any messages.
        async function saveConversationState() {{
            try {{
                const baseUrl = API_URL.replace('/api/bot', '');
                
                // Check if messageHistory contains any user messages or long assistant messages
                // If so, bot API has likely already saved messages - don't overwrite
                const hasUserMessages = messageHistory.some(m => m.role === 'user');
                const hasLongAssistant = messageHistory.some(m => 
                    m.role === 'assistant' && m.content && m.content.length > 200
                );
                
                if (hasUserMessages || hasLongAssistant) {{
                    console.warn('saveConversationState() called but messageHistory contains bot API messages. Skipping to avoid overwrite.');
                    return; // Don't save - bot API is the source of truth
                }}
                
                // Use messageHistory which preserves full content (not DOM extraction)
                const params = new URLSearchParams({{
                    session_id: sessionId,
                    ended: 'false'
                }});
                if (websiteUrl) params.append('website_url', websiteUrl);
                
                // Log message content lengths for debugging
                const messageLengths = messageHistory.map(m => ({{
                    role: m.role,
                    length: m.content ? m.content.length : 0
                }}));
                console.log('Saving conversation (welcome messages only) - session_id:', sessionId, 'messages count:', messageHistory.length, 'lengths:', messageLengths);
                
                const response = await fetch(baseUrl + '/api/conversations/save?' + params.toString(), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ messages: messageHistory }})
                }});
                
                if (!response.ok) {{
                    const errorText = await response.text();
                    console.error('Failed to save conversation:', response.status, errorText);
                    return;
                }}
                
                const data = await response.json();
                if (data.conversation_id) {{
                    currentConversationId = data.conversation_id;
                    console.log('Conversation saved successfully, ID:', currentConversationId, 'session_id:', sessionId);
                }} else {{
                    console.log('Conversation save response:', data);
                }}
            }} catch (error) {{
                console.error('Error saving conversation:', error);
            }}
        }}
        
        // Function to end chat and save as ended
        async function endChat() {{
            if (!conversationStarted) return;
            
            if (confirm('Are you sure you want to end this chat?')) {{
                try {{
                    const baseUrl = API_URL.replace('/api/bot', '');
                    // Use messageHistory instead of DOM extraction for accuracy
                    const messages = messageHistory.length > 0 ? messageHistory : [];
                    
                    const params = new URLSearchParams({{
                        session_id: sessionId,
                        ended: 'true'
                    }});
                    if (currentConversationId) params.append('conversation_id', currentConversationId);
                    
                    await fetch(baseUrl + '/api/conversations/end?' + params.toString(), {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ messages: messages }})
                    }});
                }} catch (error) {{
                    console.error('Error ending conversation:', error);
                }}
                
                // Show thank you message covering the complete widget
                const botContainer = document.getElementById('eti-bot-container');
                if (botContainer) {{
                    // Hide all views
                    homeView.style.display = 'none';
                    conversationView.style.display = 'none';
                    conversationsView.style.display = 'none';
                    inputArea.style.display = 'none';
                    bottomTabs.style.display = 'none';
                    backBtn.style.display = 'none';
                    
                    // Create overlay that covers the complete widget
                    const thankYouOverlay = document.createElement('div');
                    thankYouOverlay.id = 'eti-thank-you-overlay';
                    thankYouOverlay.style.cssText = 'position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: white; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; z-index: 1000;';
                    thankYouOverlay.innerHTML = `
                        <div style="text-align: center; max-width: 280px;">
                            <div style="margin-bottom: 24px;">
                                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#70BB32" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin: 0 auto;">
                                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                                </svg>
                            </div>
                            <h3 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 600; color: #212529;">Thank You!</h3>
                            <p style="margin: 0 0 24px 0; font-size: 14px; color: #6c757d; line-height: 1.6;">We appreciate your time. If you have any more questions, feel free to start a new conversation.</p>
                            <button id="eti-start-new-conversation-btn" style="background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; border: none; padding: 12px 24px; border-radius: 20px; cursor: pointer; font-size: 14px; font-weight: 600; transition: transform 0.2s, box-shadow 0.2s; box-shadow: 0 2px 8px rgba(3, 31, 74, 0.3); width: 100%;">
                                Start a New Conversation
                            </button>
                        </div>
                    `;
                    botContainer.appendChild(thankYouOverlay);
                    
                    // Add event listener to the new conversation button (after element is added to DOM)
                    setTimeout(() => {{
                        const startNewBtn = document.getElementById('eti-start-new-conversation-btn');
                        if (startNewBtn) {{
                            startNewBtn.addEventListener('click', () => {{
                                // Remove thank you overlay
                                const overlay = document.getElementById('eti-thank-you-overlay');
                                if (overlay) {{
                                    overlay.remove();
                                }}
                                
                                // Clear everything and go to home view
                                messagesDiv.innerHTML = '';
                                messageHistory = []; // Clear message history
                                conversationStarted = false;
                                currentConversationId = null;
                                if (endChatBtn) endChatBtn.style.display = 'none';
                                inputArea.style.display = 'none';
                                showHomeView();
                            }});
                            startNewBtn.addEventListener('mouseenter', () => {{
                                startNewBtn.style.transform = 'scale(1.02)';
                                startNewBtn.style.boxShadow = '0 4px 12px rgba(0, 44, 92, 0.4)';
                            }});
                            startNewBtn.addEventListener('mouseleave', () => {{
                                startNewBtn.style.transform = 'scale(1)';
                                startNewBtn.style.boxShadow = '0 2px 8px rgba(0, 44, 92, 0.3)';
                            }});
                        }}
                    }}, 100);
                }}
                
                // Clear conversation state
                messageHistory = []; // Clear message history
                conversationStarted = false;
                currentConversationId = null;
                if (endChatBtn) endChatBtn.style.display = 'none';
                inputArea.style.display = 'none';
                
                // Reload conversations list
                loadConversations();
            }}
        }}
        
        // Function to load conversations list
        async function loadConversations() {{
            try {{
                const baseUrl = API_URL.replace('/api/bot', '');
                const response = await fetch(baseUrl + '/api/conversations/list?session_id=' + encodeURIComponent(sessionId));
                const data = await response.json();
                
                console.log('Loaded conversations:', data);
                conversationsList.innerHTML = '';
                
                if (data.conversations && data.conversations.length > 0) {{
                    noConversations.style.display = 'none';
                    data.conversations.forEach(conv => {{
                        const convItem = document.createElement('div');
                        convItem.style.cssText = 'background: white; padding: 12px; border-radius: 8px; cursor: pointer; transition: all 0.2s; border: 1px solid #e5e7eb;';
                        
                        // Get last message preview
                        let lastMessagePreview = '';
                        if (conv.messages && conv.messages.length > 0) {{
                            const lastMsg = conv.messages[conv.messages.length - 1];
                            let msgContent = lastMsg.content || '';
                            // Strip HTML tags if any
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = msgContent;
                            msgContent = tempDiv.textContent || tempDiv.innerText || '';
                            // Escape HTML and truncate to 60 characters
                            msgContent = msgContent
                                .replace(/&/g, '&amp;')
                                .replace(/</g, '&lt;')
                                .replace(/>/g, '&gt;')
                                .replace(/"/g, '&quot;')
                                .replace(/'/g, '&#39;');
                            if (msgContent.length > 60) {{
                                lastMessagePreview = msgContent.substring(0, 60) + '...';
                            }} else {{
                                lastMessagePreview = msgContent;
                            }}
                        }}
                        
                        convItem.innerHTML = `
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                                <div style="flex: 1; min-width: 0;">
                                    <p style="margin: 0 0 4px 0; font-size: 13px; font-weight: 500; color: #212529;">${{conv.ended ? 'Ended' : 'Ongoing'}}</p>
                                    <p style="margin: 0 0 4px 0; font-size: 11px; color: #6c757d;">${{new Date(conv.created_at).toLocaleDateString()}}</p>
                                    ${{lastMessagePreview ? `<p style="margin: 0; font-size: 12px; color: #495057; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${{lastMessagePreview}}</p>` : '<p style="margin: 0; font-size: 12px; color: #9ca3af; font-style: italic;">No messages yet</p>'}}
                                </div>
                                <span style="width: 8px; height: 8px; border-radius: 50%; background: ${{conv.ended ? '#9ca3af' : '#3A621A'}}; display: inline-block; flex-shrink: 0; margin-top: 4px;"></span>
                            </div>
                        `;
                        convItem.addEventListener('click', () => {{
                            // Set conversation ID
                            currentConversationId = conv.id;
                            
                            if (conv.ended) {{
                                // Show ended conversation - display history only, no chatting allowed
                                conversationStarted = false;
                                if (endChatBtn) endChatBtn.style.display = 'none';
                                showConversationView();
                                
                                // Load messages for viewing only
                                messagesDiv.innerHTML = '';
                                if (conv.messages && conv.messages.length > 0) {{
                                    conv.messages.forEach(msg => {{
                                        const msgDiv = document.createElement('div');
                                        msgDiv.style.cssText = msg.role === 'user' 
                                            ? 'background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-end; box-shadow: 0 2px 6px rgba(3, 31, 74, 0.2);'
                                            : 'background: white; color: #031F4A; border: 1px solid #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
                                        
                                        // For assistant messages, use formatMessage to preserve formatting
                                        // For user messages, escape HTML
                                        let content = '';
                                        if (msg.role === 'assistant') {{
                                            content = formatMessage(msg.content);
                                        }} else {{
                                            // Escape HTML for user messages
                                            const escaped = msg.content
                                                .replace(/&/g, '&amp;')
                                                .replace(/</g, '&lt;')
                                                .replace(/>/g, '&gt;')
                                                .replace(/"/g, '&quot;')
                                                .replace(/'/g, '&#39;');
                                            content = `<p style="margin: 0; font-size: 13px; line-height: 1.4;">${{escaped}}</p>`;
                                        }}
                                        
                                        msgDiv.innerHTML = content;
                                        messagesDiv.appendChild(msgDiv);
                                    }});
                                }} else {{
                                    // No messages in ended conversation
                                    const noMsgDiv = document.createElement('div');
                                    noMsgDiv.style.cssText = 'background: #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start;';
                                    noMsgDiv.innerHTML = '<p style="margin: 0; font-size: 13px; color: #373D20;">This conversation has no messages.</p>';
                                    messagesDiv.appendChild(noMsgDiv);
                                }}
                                conversationView.scrollTop = conversationView.scrollHeight;
                                
                                // Hide input area - no chatting allowed for ended conversations
                                inputArea.style.display = 'none';
                                
                                // Show a message that this conversation is ended
                                const endedMsg = document.createElement('div');
                                endedMsg.style.cssText = 'background: #FFE6E8; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; margin-top: 8px;';
                                endedMsg.innerHTML = '<p style="margin: 0; font-size: 12px; color: #C20114;">This conversation has ended. Click "Chat with us" to start a new conversation.</p>';
                                messagesDiv.appendChild(endedMsg);
                                conversationView.scrollTop = conversationView.scrollHeight;
                            }} else {{
                                // Continue ongoing conversation - allow chatting
                                conversationStarted = true;
                                if (endChatBtn) endChatBtn.style.display = 'flex';
                                showConversationView();
                                
                                // Load messages and populate messageHistory
                                if (conv.messages && conv.messages.length > 0) {{
                                    messagesDiv.innerHTML = '';
                                    // Populate messageHistory from loaded conversation
                                    messageHistory = conv.messages.map(msg => ({{
                                        role: msg.role,
                                        content: msg.content,
                                        timestamp: msg.timestamp || new Date().toISOString()
                                    }}));
                                    
                                    // Display messages with proper formatting
                                    conv.messages.forEach(msg => {{
                                        const msgDiv = document.createElement('div');
                                        msgDiv.style.cssText = msg.role === 'user' 
                                            ? 'background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-end; box-shadow: 0 2px 6px rgba(3, 31, 74, 0.2);'
                                            : 'background: white; color: #031F4A; border: 1px solid #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
                                        
                                        // For assistant messages, use formatMessage to preserve formatting
                                        // For user messages, escape HTML
                                        let content = '';
                                        if (msg.role === 'assistant') {{
                                            content = formatMessage(msg.content);
                                        }} else {{
                                            // Escape HTML for user messages
                                            const escaped = msg.content
                                                .replace(/&/g, '&amp;')
                                                .replace(/</g, '&lt;')
                                                .replace(/>/g, '&gt;')
                                                .replace(/"/g, '&quot;')
                                                .replace(/'/g, '&#39;');
                                            content = `<p style="margin: 0; font-size: 13px; line-height: 1.4;">${{escaped}}</p>`;
                                        }}
                                        
                                        msgDiv.innerHTML = content;
                                        messagesDiv.appendChild(msgDiv);
                                    }});
                                    conversationView.scrollTop = conversationView.scrollHeight;
                                }}
                                
                                // Show input area for ongoing conversations
                                inputArea.style.display = 'block';
                            }}
                        }});
                        convItem.addEventListener('mouseenter', () => {{
                            convItem.style.background = '#EFF1ED';
                            convItem.style.borderColor = '#031F4A';
                        }});
                        convItem.addEventListener('mouseleave', () => {{
                            convItem.style.background = 'white';
                            convItem.style.borderColor = '#EFF1ED';
                        }});
                        conversationsList.appendChild(convItem);
                    }});
                }} else {{
                    noConversations.style.display = 'block';
                }}
            }} catch (error) {{
                console.error('Error loading conversations:', error);
                noConversations.style.display = 'block';
            }}
        }}
        
        // Update tab styles
        function updateTabStyles(activeTab) {{
            if (activeTab === 'home') {{
                // Home tab active
                homeTab.querySelector('svg').setAttribute('stroke', '#031F4A');
                homeTab.querySelector('span').style.color = '#031F4A';
                homeTab.querySelector('div:last-child').style.background = '#031F4A';
                
                // Conversations tab inactive
                conversationsTab.querySelector('svg').setAttribute('stroke', '#9ca3af');
                conversationsTab.querySelector('span').style.color = '#9ca3af';
                conversationsTab.querySelector('div:last-child').style.background = 'transparent';
            }} else {{
                // Conversations tab active
                conversationsTab.querySelector('svg').setAttribute('stroke', '#031F4A');
                conversationsTab.querySelector('span').style.color = '#031F4A';
                conversationsTab.querySelector('div:last-child').style.background = '#031F4A';
                
                // Home tab inactive
                homeTab.querySelector('svg').setAttribute('stroke', '#9ca3af');
                homeTab.querySelector('span').style.color = '#9ca3af';
                homeTab.querySelector('div:last-child').style.background = 'transparent';
            }}
        }}
        
        // Show home view by default
        function showHomeView() {{
            homeView.style.display = 'flex';
            conversationView.style.display = 'none';
            conversationsView.style.display = 'none';
            inputArea.style.display = 'none';
            bottomTabs.style.display = 'flex';
            backBtn.style.display = 'none';
            if (endChatBtn) endChatBtn.style.display = 'none';
            updateTabStyles('home');
        }}
        
        // Show conversations list view
        function showConversationsView() {{
            homeView.style.display = 'none';
            conversationView.style.display = 'none';
            conversationsView.style.display = 'flex';
            bottomTabs.style.display = 'flex';
            backBtn.style.display = 'none';
            if (endChatBtn) endChatBtn.style.display = 'none';
            updateTabStyles('conversations');
            loadConversations();
        }}
        
        // Show conversation view
        function showConversationView() {{
            homeView.style.display = 'none';
            conversationsView.style.display = 'none';
            conversationView.style.display = 'flex';
            bottomTabs.style.display = 'none';
            backBtn.style.display = 'flex';
            
            // If conversation not started, show welcome message
            if (!conversationStarted) {{
                messagesDiv.innerHTML = '';
                showWelcomeMessage();
                if (endChatBtn) endChatBtn.style.display = 'none';
                // Scroll to show buttons immediately
                setTimeout(() => {{
                    conversationView.scrollTop = conversationView.scrollHeight;
                }}, 150);
            }} else {{
                if (endChatBtn) endChatBtn.style.display = 'flex';
            }}
            
            // Show input area
            const optionsDiv = document.getElementById('eti-options');
            if (optionsDiv) optionsDiv.style.display = 'none';
            inputArea.style.display = 'block';
        }}
        
        // End chat button handler
        if (endChatBtn) {{
            endChatBtn.addEventListener('click', endChat);
            endChatBtn.addEventListener('mouseenter', () => {{
                endChatBtn.style.background = 'rgba(3, 31, 74, 0.3)';
            }});
            endChatBtn.addEventListener('mouseleave', () => {{
                endChatBtn.style.background = 'rgba(3, 31, 74, 0.2)';
            }});
        }}
        
        // Back button to go to home
        if (backBtn) {{
            backBtn.addEventListener('click', () => {{
                showHomeView();
            }});
        }}
        
        // Tab navigation
        homeTab.addEventListener('click', () => {{
            showHomeView();
        }});
        
        conversationsTab.addEventListener('click', () => {{
            showConversationsView();
        }});
        
        // Function to check for ongoing conversation and load it
        async function checkAndLoadOngoingConversation() {{
            try {{
                const baseUrl = API_URL.replace('/api/bot', '');
                const response = await fetch(baseUrl + '/api/conversations/list?session_id=' + encodeURIComponent(sessionId));
                const data = await response.json();
                
                if (data.conversations && data.conversations.length > 0) {{
                    // Find the first ongoing conversation (not ended)
                    const ongoingConv = data.conversations.find(conv => !conv.ended);
                    if (ongoingConv) {{
                        // Load the ongoing conversation
                        currentConversationId = ongoingConv.id;
                        conversationStarted = true;
                        if (endChatBtn) endChatBtn.style.display = 'flex';
                        
                        // Load messages and populate messageHistory
                        if (ongoingConv.messages && ongoingConv.messages.length > 0) {{
                            messagesDiv.innerHTML = '';
                            // Populate messageHistory from loaded conversation
                            messageHistory = ongoingConv.messages.map(msg => ({{
                                role: msg.role,
                                content: msg.content,
                                timestamp: msg.timestamp || new Date().toISOString()
                            }}));
                            
                            // Display messages with proper formatting
                            ongoingConv.messages.forEach(msg => {{
                                const msgDiv = document.createElement('div');
                                msgDiv.style.cssText = msg.role === 'user' 
                                    ? 'background: linear-gradient(135deg, #031F4A 0%, #3A621A 100%); color: white; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-end; box-shadow: 0 2px 6px rgba(3, 31, 74, 0.2);'
                                    : 'background: white; color: #031F4A; border: 1px solid #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
                                
                                // For assistant messages, use formatMessage to preserve formatting
                                // For user messages, escape HTML
                                let content = '';
                                if (msg.role === 'assistant') {{
                                    content = formatMessage(msg.content);
                                }} else {{
                                    // Escape HTML for user messages
                                    const escaped = msg.content
                                        .replace(/&/g, '&amp;')
                                        .replace(/</g, '&lt;')
                                        .replace(/>/g, '&gt;')
                                        .replace(/"/g, '&quot;')
                                        .replace(/'/g, '&#39;');
                                    content = `<p style="margin: 0; font-size: 13px; line-height: 1.4;">${{escaped}}</p>`;
                                }}
                                
                                msgDiv.innerHTML = content;
                                messagesDiv.appendChild(msgDiv);
                            }});
                            conversationView.scrollTop = conversationView.scrollHeight;
                            inputArea.style.display = 'block';
                            return true; // Ongoing conversation loaded
                        }}
                    }}
                }}
                return false; // No ongoing conversation found
            }} catch (error) {{
                console.error('Error checking ongoing conversation:', error);
                return false;
            }}
        }}
        
        // Chat with us button - navigate to conversation (shows welcome message or ongoing chat)
        if (chatWithUsBtn) {{
            chatWithUsBtn.addEventListener('click', async () => {{
                showConversationView();
                
                // Check if there's an ongoing conversation
                const hasOngoing = await checkAndLoadOngoingConversation();
                
                if (!hasOngoing) {{
                    // No ongoing conversation (all ended or no conversations), start a NEW conversation
                    conversationStarted = false;
                    currentConversationId = null; // Clear any previous conversation ID to ensure new one is created
                    messagesDiv.innerHTML = '';
                    if (inputArea) inputArea.style.display = 'block';
                    if (endChatBtn) endChatBtn.style.display = 'flex';
                    showWelcomeMessage();
                    // Scroll to show welcome message immediately
                    setTimeout(() => {{
                        conversationView.scrollTop = conversationView.scrollHeight;
                    }}, 150);
                }}
            }});
            
            // Hover effects for chat with us button
            chatWithUsBtn.addEventListener('mouseenter', () => {{
                chatWithUsBtn.style.transform = 'scale(1.02)';
                chatWithUsBtn.style.boxShadow = '0 4px 12px rgba(0, 44, 92, 0.4)';
            }});
            chatWithUsBtn.addEventListener('mouseleave', () => {{
                chatWithUsBtn.style.transform = 'scale(1)';
                chatWithUsBtn.style.boxShadow = '0 2px 8px rgba(0, 44, 92, 0.3)';
            }});
        }}
        
        // Toggle chat
        toggleBtn.addEventListener('click', () => {{
            container.style.display = container.style.display === 'none' ? 'flex' : 'none';
            toggleBtn.style.display = container.style.display === 'flex' ? 'none' : 'flex';
            if (container.style.display === 'flex') {{
                showHomeView(); // Show home view when opening
                hideTooltip(); // Hide tooltip when opening widget
                toggleBtn.style.transform = 'scale(0.95)';
                setTimeout(() => {{ toggleBtn.style.transform = 'scale(1)'; }}, 200);
            }} else {{
                // Show tooltip again when closing widget (if not dismissed)
                setTimeout(() => {{
                    showTooltip();
                }}, 300);
            }}
        }});
        
        closeBtn.addEventListener('click', () => {{
            container.style.display = 'none';
            toggleBtn.style.display = 'flex';
            // Show tooltip again when closing widget (if not dismissed)
            setTimeout(() => {{
                showTooltip();
            }}, 300);
        }});
        
        // Hover effects for send button
        if (sendBtn) {{
            sendBtn.addEventListener('mouseenter', () => {{
                sendBtn.style.transform = 'scale(1.05)';
                sendBtn.style.boxShadow = '0 4px 12px rgba(0, 44, 92, 0.4)';
            }});
            sendBtn.addEventListener('mouseleave', () => {{
                sendBtn.style.transform = 'scale(1)';
                sendBtn.style.boxShadow = '0 2px 8px rgba(0, 44, 92, 0.3)';
        }});
        }}
        
        
        // Send message
        async function sendMessage() {{
            const message = input.value.trim();
            if (!message) return;
            
            // Hide options if visible
            const optionsDiv = document.getElementById('eti-options');
            if (optionsDiv) optionsDiv.style.display = 'none';
            
            // Mark conversation as started
            if (!conversationStarted) {{
                conversationStarted = true;
                if (endChatBtn) endChatBtn.style.display = 'flex';
            }}
            
            // Add user message
            const userMsg = document.createElement('div');
            userMsg.style.cssText = 'background: linear-gradient(135deg, #031F4A 0%, #70BB32 100%); color: white; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-end; box-shadow: 0 2px 6px rgba(3, 31, 74, 0.2);';
            userMsg.innerHTML = `<p style="margin: 0; font-size: 13px; line-height: 1.4;">${{message}}</p>`;
            messagesDiv.appendChild(userMsg);
            conversationView.scrollTop = conversationView.scrollHeight;
            
            // Add to message history (for local tracking only)
            messageHistory.push({{
                role: 'user',
                content: message,
                timestamp: new Date().toISOString()
            }});
            
            // NOTE: User message will be saved by bot API when it responds
            // Don't call saveConversationState() here to avoid overwriting
            
            input.value = '';
            sendBtn.disabled = true;
            sendBtn.style.opacity = '0.6';
            
            // Add typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.id = 'eti-typing-indicator';
            typingIndicator.style.cssText = 'background: white; color: #031F4A; border: 1px solid #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
            typingIndicator.innerHTML = `
                <div style="display: flex; align-items: center; gap: 4px; font-size: 13px; color: #031F4A;">
                    <span style="width: 8px; height: 8px; background: #3A621A; border-radius: 50%; display: inline-block; animation: typing-dot 1.4s infinite ease-in-out;"></span>
                    <span style="width: 8px; height: 8px; background: #3A621A; border-radius: 50%; display: inline-block; animation: typing-dot 1.4s infinite ease-in-out; animation-delay: 0.2s;"></span>
                    <span style="width: 8px; height: 8px; background: #3A621A; border-radius: 50%; display: inline-block; animation: typing-dot 1.4s infinite ease-in-out; animation-delay: 0.4s;"></span>
                </div>
            `;
            messagesDiv.appendChild(typingIndicator);
            conversationView.scrollTop = conversationView.scrollHeight;
            
            try {{
                const response = await fetch(API_URL + '/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        message: message,
                        session_id: sessionId,
                        website_url: websiteUrl,
                        user_ip: null,
                        user_agent: navigator.userAgent
                    }})
                }});
                
                const data = await response.json();
                
                // Remove typing indicator
                const typingEl = document.getElementById('eti-typing-indicator');
                if (typingEl) {{
                    typingEl.remove();
                }}
                
                // Add bot response with formatted markdown
                const botMsg = document.createElement('div');
                botMsg.style.cssText = 'background: white; color: #031F4A; border: 1px solid #EFF1ED; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
                botMsg.innerHTML = `<div style="font-size: 13px; color: #031F4A; line-height: 1.5;">${{formatMessage(data.response)}}</div>`;
                messagesDiv.appendChild(botMsg);
                conversationView.scrollTop = conversationView.scrollHeight;
                
                // Add to message history with full content (before formatting)
                messageHistory.push({{
                    role: 'assistant',
                    content: data.response, // Use original response, not formatted HTML
                    timestamp: new Date().toISOString()
                }});
                
                // NOTE: Bot API already saves messages correctly to MongoDB using $push
                // DO NOT call saveConversationState() here as it would overwrite with $set
                // The bot API preserves full message content correctly
            }} catch (error) {{
                console.error('Error sending message:', error);
                
                // Remove typing indicator
                const typingEl = document.getElementById('eti-typing-indicator');
                if (typingEl) {{
                    typingEl.remove();
                }}
                
                const errorMsg = document.createElement('div');
                errorMsg.style.cssText = 'background: #FFE6E8; padding: 10px 14px; border-radius: 16px; max-width: 80%; align-self: flex-start; box-shadow: 0 1px 2px rgba(3, 31, 74, 0.05);';
                errorMsg.innerHTML = `<p style="margin: 0; font-size: 13px; color: #C20114; line-height: 1.4;">Sorry, there was an error. Please try again.</p>`;
                messagesDiv.appendChild(errorMsg);
                conversationView.scrollTop = conversationView.scrollHeight;
            }} finally {{
                sendBtn.disabled = false;
                sendBtn.style.opacity = '1';
            }}
        }}
        
        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keypress', (e) => {{
            if (e.key === 'Enter') sendMessage();
        }});
    }}
}})();
"""  # noqa: RUF001, W291  # nosec B608  # embedded JS/CSS asset: close glyph is rendered in the UI

    response = Response(content=widget_js.strip(), media_type="application/javascript")
    # Add cache control headers to prevent caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
