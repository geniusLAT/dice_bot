import telebot
import random
file=open("token.txt",'r')
token=file.read()#''
file.close()
bot=telebot.TeleBot(token)
@bot.message_handler(commands=['start'])
def start_message(message):
  bot.send_message(message.chat.id,"Привет ✌️ ")

def d4():
  random.seed(random.randint(1,4)) 
  return str(random.randint(1,4))

def d10():
   random.seed(random.randint(1,1000)) 
   return str(random.randint(1,10))

def d8():
  random.seed(random.randint(1,1000)) 
  return str(random.randint(1,8))


def d12():
   random.seed(random.randint(1,1000)) 
   return str(random.randint(1,12))


def d20():
   random.seed(random.randint(1,1000)) 
   return str(random.randint(1,20))

Aloweded_symbols="0123456789 +-*/()d"
def show_result(text:str):
  print("")
  formula = "d0()"
  if "d10()" in text:
    formula="d10()"
  if "d12()" in text:
    formula="d12()"
  if "d4()" in text:
    formula="d4()"
  if "d8()" in text:
    formula="d8()"
  if "d20()" in text:
    formula="d20()"


  for_num = text.find(formula)
  for_num_end = for_num+len(formula)
  print(for_num)
  toeval=text[for_num:for_num_end]
  print( toeval)

  end_num=for_num_end

  while True:
     if end_num+1>len(text)-1: break
     if not text[end_num+1] in (Aloweded_symbols): break

     end_num+=1
  start_num = for_num
  while True:
     if start_num-1==-1: break
     if not text[start_num-1] in (Aloweded_symbols): break

     start_num-=1


  toeval=text[start_num:end_num]
  print( toeval)

  answer=toeval

  try:
    while formula in toeval:
      result=str(eval(formula))
      print(result)
      toeval=toeval.replace(formula,result,1)
    answer+="="+toeval
  except:
    raise Exception("bad formula")

  try:
    result=str(eval(toeval))
    if result!=toeval:
      answer +="="+result
  except Exception as e:
    print(str(e))
   
    if ("never closed" in str(e)):
      answer+='\n Забыли закрыть скобку'
    if ( "Perhaps you forgot a comma" in str(e)):
      answer+='\n Тут пустое действие у скобки, оно не считается'
    if ( "unsupported operand type" in str(e)):
      answer+='\n Тут пустое выражение вскобках, оно не считается'
    if ( "unmatched ')'" in str(e)):
      answer+='\n Забыли открыть скобку'
    if ( "invalid syntax ')'" in str(e)):
      answer+='\n Математическая проблема'
    
  print(answer)
  return str(answer)
   

    
    
   


@bot.message_handler(content_types='text')
def message_reply(message):
    if ("d10()" in message.text) or ("d8()" in message.text) or ("d4()" in message.text) or ("d12()" in message.text) or ("d20()" in message.text) :
      try:    bot.send_message(message.chat.id,show_result(message.text))
      except Exception as e: print(e)
bot.infinity_polling()
        
#print(show_result(" sdsd (2/3)+(3 + (5)+d20())*7+2**2 hdfhd"))
#print(show_result("d10()"))
