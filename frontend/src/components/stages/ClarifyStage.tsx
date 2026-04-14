import { useState } from 'react'
import { useProjectStore } from '@/store/projectStore'
import { askClarificationQuestion, getProject, answerQuestion, skipQuestion, doneClarification } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Badge } from '../ui/Badge'
import { Loader2, Send, FastForward } from 'lucide-react'
import type { Question } from '@/types'

export function ClarifyStage() {
  const { currentProject, setCurrentProject, setIsLoading, setError } = useProjectStore()
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [skipReasons, setSkipReasons] = useState<Record<string, string>>({})
  const [userQuestion, setUserQuestion] = useState('')
  const [userAnswer, setUserAnswer] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const questions = currentProject?.questions || []

  const handleAnswer = async (questionId: string) => {
    const answer = answers[questionId]
    if (!answer?.trim() || !currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await answerQuestion(currentProject.id, { question_id: questionId, answer })
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
      setAnswers({ ...answers, [questionId]: '' })
    } catch (error: any) {
      setError(`Failed to submit answer: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleSkip = async (questionId: string) => {
    const reason = skipReasons[questionId]
    if (!reason?.trim() || !currentProject) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await skipQuestion(currentProject.id, { question_id: questionId, reason })
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
      setSkipReasons({ ...skipReasons, [questionId]: '' })
    } catch (error: any) {
      setError(`Failed to skip question: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleDone = async () => {
    if (!currentProject) return

    const openQuestions = questions.filter((q: Question) => q.status === 'open')
    if (openQuestions.length > 0 && !confirm(`You still have ${openQuestions.length} unanswered questions. Continue anyway?`)) {
      return
    }

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      await doneClarification(currentProject.id)
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
    } catch (error: any) {
      setError(`Failed to complete clarification: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const handleAskQuestion = async () => {
    if (!currentProject || !userQuestion.trim()) return

    try {
      setIsSubmitting(true)
      setIsLoading(true)
      const result = await askClarificationQuestion(currentProject.id, { question: userQuestion })
      const updated = await getProject(currentProject.id)
      setCurrentProject(updated)
      setUserAnswer(result.answer || '')
      setUserQuestion('')
    } catch (error: any) {
      setError(`Failed to ask question: ${error}`)
    } finally {
      setIsSubmitting(false)
      setIsLoading(false)
    }
  }

  const openQuestions = questions.filter((q: Question) => q.status === 'open')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stage 2: Clarification ({openQuestions.length} remaining)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {questions.length === 0 ? (
          <p className="text-center text-muted-foreground">No questions generated. You can proceed to the next stage.</p>
        ) : (
          <div className="space-y-4">
            {questions.map((question: Question) => (
              <div key={question.id} className={`rounded-md border p-4 ${question.status === 'open' ? '' : 'opacity-50'}`}>
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{question.id}</span>
                      <Badge variant={question.status === 'open' ? 'default' : 'secondary'}>
                        {question.status}
                      </Badge>
                    </div>
                    <p className="mt-2 text-lg">{question.question}</p>
                    {question.context && (
                      <p className="mt-2 text-sm text-muted-foreground">{question.context}</p>
                    )}
                  </div>
                </div>

                {question.status === 'open' && (
                  <div className="mt-4 flex flex-col gap-3">
                    <Input
                      placeholder="Type your answer here..."
                      value={answers[question.id] || ''}
                      onChange={(e) => setAnswers({ ...answers, [question.id]: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          handleAnswer(question.id)
                        }
                      }}
                    />
                    <div className="flex justify-between">
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleAnswer(question.id)}
                          disabled={!answers[question.id] || isSubmitting}
                        >
                          <Send className="mr-2 h-4 w-4" />
                          Answer
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            if (confirm('Skip this question?')) {
                              handleSkip(question.id)
                            }
                          }}
                          disabled={isSubmitting}
                        >
                          <FastForward className="mr-2 h-4 w-4" />
                          Skip
                        </Button>
                      </div>
                    </div>
                    <Input
                      placeholder="Reason for skipping (optional)..."
                      value={skipReasons[question.id] || ''}
                      onChange={(e) => setSkipReasons({ ...skipReasons, [question.id]: e.target.value })}
                      className="mt-2"
                    />
                  </div>
                )}

                {question.status === 'answered' && question.answer && (
                  <div className="mt-3 rounded-md bg-muted p-3">
                    <p className="text-sm font-medium">Your answer:</p>
                    <p className="mt-1 text-sm">{question.answer}</p>
                  </div>
                )}

                {question.status === 'skipped' && question.skip_reason && (
                  <div className="mt-3 rounded-md bg-muted p-3">
                    <p className="text-sm font-medium">Skipped:</p>
                    <p className="mt-1 text-sm text-muted-foreground">{question.skip_reason}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="rounded-md border p-4">
          <h3 className="mb-2 font-semibold">Ask your own question</h3>
          <p className="mb-3 text-sm text-muted-foreground">
            Ask planning questions in context, for example: "Can we fit reporting into Sprint 2?"
          </p>
          <div className="flex gap-2">
            <Input
              placeholder="Type your question..."
              value={userQuestion}
              onChange={(e) => setUserQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleAskQuestion()
                }
              }}
            />
            <Button onClick={handleAskQuestion} disabled={!userQuestion.trim() || isSubmitting}>
              Ask
            </Button>
          </div>
          {userAnswer && (
            <div className="mt-3 rounded-md bg-muted p-3">
              <p className="text-sm font-medium">Answer:</p>
              <p className="mt-1 text-sm">{userAnswer}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end border-t pt-4">
          <Button onClick={handleDone} disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Done & Continue to SoW
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}