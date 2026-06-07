// PAST: The app.js file had single static scripts for each feeling category and no switcher.
// ISSUE: The user felt there were too few variations (1-3) and wanted to see the depth of the script variations (Soft, Firm, Protective) on the landing page results.
// PRESENT: Expanded the script database to include Soft & Warm, Clear & Firm, and Protective script levels for every feeling category, and added dynamic tab switching handlers.
// RATIONALE: This shows the user the three structural levels of boundaries, providing quick value and mirroring the ebook structure while keeping the interface interactive and engaging.

// Data mapping feelings to custom diagnoses and scripts
const diagnosisData = {
    work: {
        title: "You’re carrying the weight of the whole team, sis. 💼",
        description: "You want to do a good job, and you want to be seen as reliable. But right now, you are being treated as a resource rather than a person. When you say 'yes' to every late request and boundary-crossing project, your body and peace pay the bill. Your boss has the power, but *you* have the right to log off. This script frames your limit around quality, making it professional and non-negotiable.",
        scripts: {
            soft: `I’d love to help with this, but my plate is currently full with [Project A] and [Project B]. To make sure I maintain the quality of those projects, I won't be able to take this on right now. Can we discuss adjusting timelines for my other work?`,
            firm: `I cannot take on [New Task] right now as my capacity is fully committed to [Project A] and [Project B]. If this new task is a higher priority, let's discuss which of the current projects we should put on hold to free up my time.`,
            protective: `I don't have the capacity to take on additional tasks at this time. I will let you know when my current projects are completed and I have room for more.`
        }
    },
    home: {
        title: "You are a partner, not a project manager. 🏡",
        description: "You are a partner, not an executive assistant. Remembering to buy the toilet paper, tracking grocery lists, and constantly reminding others to do their chores is mental labor. That is why you feel mentally exhausted even when sitting on the couch. It's time to hand over the entire project (conception, planning, and execution), not just wait for you to delegate. Use this to shift the load.",
        scripts: {
            soft: `Hey! My mental bandwidth is completely maxed out this week. I need you to take full ownership of dinner on Wednesday and Thursday. That means planning what we're eating, checking ingredients, and cooking. I'd love to just sit down and eat with you without having to manage it! Can you do that for us?`,
            firm: `Hey, I need to step back from managing the household chores. I need you to fully own [Task, e.g., groceries/laundry] going forward—from noticing when it's needed to getting it done. If I have to remind or guide you, the mental load is still on me, and I need a true partnership.`,
            protective: `I am feeling overwhelmed by the household load and cannot manage it alone anymore. I need us to divide the responsibilities clearly so we each own our parts from start to finish without reminders.`
        }
    },
    social: {
        title: "Your battery is in the red, and that is okay. 🔋",
        description: "You love your friends and want to see them happy. But right now, your own container is empty. Going to this event will make them happy for a few hours, but it will leave you running on fumes for days. A true friend wants you to rest. Your energy is a precious, limited resource, and protecting it is an act of love to yourself. Send this to decline with warmth.",
        scripts: {
            soft: `I’m so grateful you invited me, and I would love to catch up! I’ve had a really intense week and need to use this weekend to recharge my battery, so I won't be able to make it. Let's definitely grab coffee or lunch next week when my battery is back to 100%! 💖`,
            firm: `Thank you for the invite! I won't be able to make it this time as I'm keeping my schedule clear this weekend to rest. I hope you guys have a wonderful time!`,
            protective: `I can't make it to the event. Thank you for understanding my need to take some quiet time for myself.`
        }
    },
    family: {
        title: "Family is complicated. Your peace is simple. 👨‍👩‍👧",
        description: "It is so hard to say 'no' to family because their expectations are loaded with years of history. You might feel like a bad daughter, sister, or partner. But loving them doesn't mean you have to be available at the cost of your own mental health. Setting a boundary with family isn't pushing them away—it is keeping them close in a way that doesn't build resentment.",
        scripts: {
            soft: `I love you guys so much, and because I love you, I want to make sure when we hang out I am fully present and not a stressed-out mess. My schedule is completely overwhelmed right now, so I won't be able to help out this weekend. Let's schedule a call or visit on [specific day] instead!`,
            firm: `I understand that you need help with this, but I'm not available to take it on right now. I need to protect my schedule, so my answer has to be no this time. I hope you can find another way to get it sorted.`,
            protective: `I cannot help with that. I care about you, but I have to hold this boundary for my own well-being, and I'm not open to negotiating it.`
        }
    },
    sorry: {
        title: "You do not need to apologize for taking up space. 💬",
        description: "We say 'sorry' when we reply a few hours late, when we ask a question, or when we simply have a preference. Every time you apologize for existing, you subconsciously tell your brain that you've done something wrong. You haven't. It is time to replace apologies with appreciation and step back into your own authority.",
        scripts: {
            soft: `[Instead of apologizing for a late reply]:\n"Thank you for your patience on this!"\n\n[Instead of apologizing for asking for help]:\n"Thank you so much for taking a look at this with me!"\n\n[Instead of apologizing for catching an error]:\n"Thank you for catching that error!"`,
            firm: `[To stop apologizing at work]:\n"Thanks for calling that out, I've updated the file."\n\n[To stop apologizing when declining]:\n"I cannot make it, but thank you for thinking of me."\n\n[To stop apologizing for expressing a preference]:\n"I actually prefer we try [Option B].引领"`,
            protective: `[To handle pushback without apologizing]:\n"I remember it this way, and I'm not going to argue about my experience."\n\n[To hold space without saying sorry]:\n"My boundary is still the same. I'm not discussing this further."`
        }
    }
};

// DOM Elements
const feelingForm = document.getElementById('feeling-form');
const quizCard = document.getElementById('quiz-card');
const resultsCard = document.getElementById('results-card');
const resultsLoading = document.getElementById('results-loading');
const resultsActual = document.getElementById('results-actual');

const diagnosisTitle = document.getElementById('diagnosis-title');
const diagnosisDescription = document.getElementById('diagnosis-description');
const scriptContent = document.getElementById('script-content');

const copyScriptBtn = document.getElementById('copy-script-btn');
const quizBackBtn = document.getElementById('quiz-back-btn');

// Switcher state
let currentFeeling = '';
let currentLevel = 'soft';

// Get switcher buttons
const switcherBtns = document.querySelectorAll('.switcher-btn');

// Switcher Button click handler
switcherBtns.forEach(btn => {
    btn.addEventListener('click', function() {
        // Remove active class from all buttons
        switcherBtns.forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-checked', 'false');
        });
        
        // Add active class to clicked button
        this.classList.add('active');
        this.setAttribute('aria-checked', 'true');
        
        // Get level and update content
        currentLevel = this.getAttribute('data-level');
        updateScriptText();
    });
});

function updateScriptText() {
    if (!currentFeeling) return;
    const scripts = diagnosisData[currentFeeling].scripts;
    scriptContent.textContent = scripts[currentLevel] || scripts.soft;
}

// Form Submit Handler
feelingForm.addEventListener('submit', function(e) {
    e.preventDefault();
    
    // Get selected feeling
    const selectedFeeling = document.querySelector('input[name="feeling"]:checked').value;
    const data = diagnosisData[selectedFeeling];
    
    if (!data) return;

    currentFeeling = selectedFeeling;
    currentLevel = 'soft'; // Reset to soft default on new quiz submission

    // Reset switcher active classes
    switcherBtns.forEach(btn => {
        if (btn.getAttribute('data-level') === 'soft') {
            btn.classList.add('active');
            btn.setAttribute('aria-checked', 'true');
        } else {
            btn.classList.remove('active');
            btn.setAttribute('aria-checked', 'false');
        }
    });

    // Transition to results screen
    quizCard.classList.add('hidden');
    resultsCard.classList.remove('hidden');
    resultsLoading.classList.remove('hidden');
    resultsActual.classList.add('hidden');

    // Simulate "pouring tea" loading state for a human touch (1.2 seconds)
    setTimeout(() => {
        // Populate content
        diagnosisTitle.textContent = data.title;
        diagnosisDescription.textContent = data.description;
        updateScriptText();

        // Reveal actual results
        resultsLoading.classList.add('hidden');
        resultsActual.classList.remove('hidden');
    }, 1200);
});

// Copy to Clipboard Handler
copyScriptBtn.addEventListener('click', async function() {
    const textToCopy = scriptContent.textContent;
    
    try {
        await navigator.clipboard.writeText(textToCopy);
        
        // Show success visual state
        copyScriptBtn.classList.add('copied');
        copyScriptBtn.innerHTML = `
            <i class="ri-checkbox-circle-line btn-icon"></i>
            <span class="btn-text">Copied! Reclaim that peace 💖</span>
        `;
        
        // Reset button after 2.5 seconds
        setTimeout(() => {
            copyScriptBtn.classList.remove('copied');
            copyScriptBtn.innerHTML = `
                <i class="ri-clipboard-line btn-icon"></i>
                <span class="btn-text">Copy Script</span>
            `;
        }, 2500);
        
    } catch (err) {
        console.error('Failed to copy text: ', err);
    }
});

// Back Button Handler
quizBackBtn.addEventListener('click', function() {
    // Transition back to quiz
    resultsCard.classList.add('hidden');
    quizCard.classList.remove('hidden');
    
    // Reset form selection
    feelingForm.reset();
    currentFeeling = '';
});

// PAST: There was no FAQ section or interactive accordion in the application.
// ISSUE: Potential buyers had unanswered objections (e.g., download delivery, customization, handling pushback), leading to higher exit rates.
// PRESENT: Added an interactive FAQ accordion handler that toggles aria-expanded and active class states.
// RATIONALE: Solving buyer objections directly on the landing page through a clean, space-saving accordion layout increases user confidence and conversion rates.
const faqTriggers = document.querySelectorAll('.faq-trigger');

faqTriggers.forEach(trigger => {
    trigger.addEventListener('click', function() {
        const parent = this.parentElement;
        const isExpanded = this.getAttribute('aria-expanded') === 'true';
        
        // Toggle current item
        this.setAttribute('aria-expanded', !isExpanded);
        parent.classList.toggle('active');
        
        // Close other accordion items to keep the layout neat
        faqTriggers.forEach(otherTrigger => {
            if (otherTrigger !== this) {
                otherTrigger.setAttribute('aria-expanded', 'false');
                otherTrigger.parentElement.classList.remove('active');
            }
        });
    });
});

// Outcomes Selector Section Tab Switcher
const outcomeTabs = document.querySelectorAll('.outcome-tab');
const outcomePanels = document.querySelectorAll('.outcome-panel');

outcomeTabs.forEach(tab => {
    tab.addEventListener('click', function() {
        // Remove active class and set aria-selected false for all tabs
        outcomeTabs.forEach(t => {
            t.classList.remove('active');
            t.setAttribute('aria-selected', 'false');
        });
        
        // Hide all panels
        outcomePanels.forEach(p => {
            p.classList.remove('active');
            p.style.display = 'none';
        });
        
        // Activate clicked tab
        this.classList.add('active');
        this.setAttribute('aria-selected', 'true');
        
        // Show corresponding panel
        const outcomeId = this.getAttribute('data-outcome');
        const activePanel = document.getElementById(`outcome-panel-${outcomeId}`);
        if (activePanel) {
            activePanel.classList.add('active');
            activePanel.style.display = 'block';
        }
    });
});




