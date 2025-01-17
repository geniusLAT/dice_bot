import telebot
import random
file=open("token.txt",'r')
token=file.read().strip()#''

for letter in token:
  print(f" letter {letter} :{ord(letter)}")

file.close()
bot=telebot.TeleBot(token)
@bot.message_handler(commands=['start'])
def start_message(message):
  bot.send_message(message.chat.id,"Привет ✌️ ")

def From_DnD_to_Py(text:str):
  num_letter="0123456789"
  text=text.replace('к','d')
  while ("d10()" in text) or ("d8()" in text) or ("d4()" in text) or ("d12()" in text) or ("d20()" in text) or ("d6()" in text)or ("d100()" in text):
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
    if "d6()" in text:
      formula="d6()"
    if "d100()" in text:
      formula="d100()"

    end_num=start_num = text.find(formula)
    
    print("num:"+text[start_num:end_num])
    
    while True:
      if start_num==0: break
      if not text[start_num-1] in num_letter: break
      start_num-=1

    print("num:"+text[start_num:end_num])

    new_formula=formula[:-1]+text[start_num:end_num]+" )"
    print(new_formula)
    #for i in range(start_num,end_num):text[i]=" "

    text=text.replace(text[start_num:end_num]+formula,new_formula,1)

    #break
    


  return text



#print(From_DnD_to_Py("dfdsf d10() sfsf"))
#print(From_DnD_to_Py("sssd r5d10()ddd"))
#print(From_DnD_to_Py("123d10()"))

def find_local_formula(text:str):
  local_formula = "d0()"
  if "d10(" in text:
    local_formula="d10("
    
  if "d12(" in text:
    local_formula="d12("
  if "d4(" in text:
    local_formula="d4("
  if "d8(" in text:
    local_formula="d8("
  if "d20(" in text:
    local_formula="d20("
  if "d6(" in text:
    local_formula="d6("
  if "d100(" in text:
    local_formula="d100("


  lf_start=text.find(local_formula)
  second_part= text.split(local_formula)[1]
  print("second_part:"+second_part)
  lf_end = second_part.find(")")
  print(lf_end)
  print(lf_start+len(local_formula)+lf_end)
  print("local formula: "+text[lf_start:lf_start+len(local_formula)+lf_end+1])
  if lf_end==-1: raise Exception("Wrong local formula")
  return text[lf_start:lf_start+len(local_formula)+lf_end+1]

#print(find_local_formula(" ahksdshd d10(55656) dfdfhh"))
def dn(n,q=1):
  r=0
  
  for i in range(q):
    random.seed(random.randint(1,1000)) 
    r+=random.randint(1,n)
  return r
def d4(q:int =1):
  return str(dn(4,q))

def d10(q:int =1):
   
   return str(dn(10,q))

def d8(q:int =1):
  
  return str(dn(8,q))


def d12(q:int =1):
   return str(dn(12,q))



def d20(q:int =1):
   return str(dn(20,q))

def d6(q:int =1):
   return str(dn(6,q))

def d100(q:int =1):
   return str(dn(100,q))


Aloweded_symbols="0123456789 +-*/()dк."
def show_result(text:str):
  text+="s"
  #text=From_DnD_to_Py(text)
  
  print("")
  formula = "d0("
  if "d10(" in text:
    formula="d10("
  if "d12(" in text:
    formula="d12("
  if "d4(" in text:
    formula="d4("
  if "d8(" in text:
    formula="d8("
  if "d20(" in text:
    formula="d20("
  if "d6(" in text:
    formula="d6("
  if "d100(" in text:
    formula="d100("


  for_num = text.find(formula)
  for_num_end = for_num+len(formula)
  print(for_num)
  toeval=text[for_num:for_num_end]
  print( toeval)

  end_num=for_num_end

  while True:
     if end_num+1==len(text): break
     if not text[end_num+1] in (Aloweded_symbols): 
      print(text[end_num+1] +" is not allowded")
      end_num+=1
      break

     end_num+=1
  start_num = for_num
  while True:
     if start_num-1==-1: break
     if not text[start_num-1] in (Aloweded_symbols): break

     start_num-=1


  toeval=text[start_num:end_num]
  print( toeval)

  answer=toeval
  toeval=From_DnD_to_Py(toeval)
  try:
    c=102
    while ("d10(" in toeval) or ("d8(" in toeval) or ("d4(" in toeval) or ("d12(" in toeval) or ("d20(" in toeval)or ("d6(" in toeval)or ("d100(" in toeval):
      local_formula =find_local_formula(toeval)
      c-=1
      if c==0: break
      result=str(eval(local_formula))
      print(result)
      toeval=toeval.replace(local_formula,result,1)
      print(toeval)
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
    print("msg")
    if ("d10()" in message.text) or ("d8()" in message.text) or ("d4()" in message.text) or ("d12()" in message.text) or ("d20()" in message.text) or ("d6()" in message.text) or ("d100()" in message.text) :
      try:    bot.send_message(message.chat.id,show_result(message.text),reply_to_message_id=message.id)
      except Exception as e: print(e)
bot.infinity_polling()


#print(show_result(" sdsdt (2/3)+(3 + (5)+2d20())*7+2**2 hdfhd"))
#print(show_result("d10()"))
